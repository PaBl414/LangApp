"""
Endpointy: lista języków, języki użytkownika.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dictionary_service import dictionary
from ..models import Language, UserLanguage, User, UserWord, StudySession, StudyAnswer, Progress, WordReview
from ..schemas import AddLanguageRequest, AddWordRequest, ImportWordsRequest
from ..grading import accepted_variants, clean_text, normalize_answer
from ..reviews import word_signature
from .learning import current_user

router = APIRouter(prefix="/api", tags=["languages"])


async def lock_vocabulary(db: AsyncSession, user_id: int, language_id: int) -> None:
    """Serialize vocabulary writers on the owned membership before reading words.

    A no-op UPDATE acquires SQLite's write lock (or the row lock on other DBs).
    This also makes retries of imports safe without a vocabulary schema change.
    """
    result = await db.execute(update(UserLanguage).where(
        UserLanguage.user_id == user_id, UserLanguage.language_id == language_id,
    ).values(language_id=language_id))
    if not result.rowcount:
        raise HTTPException(404, "Ten język nie jest dodany do Twojego profilu.")


async def duplicate_word(db: AsyncSession, user_id: int, language_id: int, primary: str, exclude_id: int | None = None) -> bool:
    rows = (await db.execute(select(UserWord.id, UserWord.word).where(
        UserWord.user_id == user_id, UserWord.language_id == language_id,
    ))).all()
    key = normalize_answer(primary)
    return any(row.id != exclude_id and normalize_answer(row.word) == key for row in rows)


async def cached_confirmation(db: AsyncSession, language_id: int, word: str) -> bool:
    language = await db.get(Language, language_id)
    return bool(language and dictionary.confirmed(language.code, word))


@router.get("/languages")
async def all_languages(db: AsyncSession = Depends(get_db)):
    """Pełna lista 50 języków — do wyboru przy dodawaniu."""
    rows = (await db.execute(
        select(Language).where(Language.is_active == True).order_by(Language.name_pl)
    )).scalars().all()
    return [
        {"id": l.id, "code": l.code, "name_pl": l.name_pl,
         "name_native": l.name_native, "flag": l.flag_emoji}
        for l in rows
    ]


@router.get("/user/languages")
async def my_languages(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Języki dodane przez zalogowanego użytkownika."""
    stmt = (
        select(Language, UserLanguage.id)
        .join(UserLanguage, UserLanguage.language_id == Language.id)
        .where(UserLanguage.user_id == user.id)
        .order_by(UserLanguage.created_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {"id": lang.id, "code": lang.code, "name_pl": lang.name_pl,
         "name_native": lang.name_native, "flag": lang.flag_emoji,
         "user_language_id": ul_id}
        for lang, ul_id in rows
    ]


@router.post("/user/languages")
async def add_language(
    payload: AddLanguageRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dodaj język do profilu użytkownika. Body: {"language_id": 3}"""
    lang_id = payload.language_id

    lang = (await db.execute(select(Language).where(Language.id == lang_id))).scalar_one_or_none()
    if not lang or not lang.is_active:
        raise HTTPException(404, "Język nie istnieje.")

    dup = (await db.execute(
        select(UserLanguage).where(
            UserLanguage.user_id == user.id,
            UserLanguage.language_id == lang_id,
        )
    )).scalar_one_or_none()
    if dup:
        raise HTTPException(409, "Ten język jest już dodany.")

    ul = UserLanguage(user_id=user.id, language_id=lang_id)
    db.add(ul)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Ten język jest już dodany.")
    await db.refresh(ul)
    return {"ok": True, "user_language_id": ul.id, "language_id": lang_id}


@router.delete("/user/languages/{user_language_id}")
async def remove_language(
    user_language_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ul = (await db.execute(
        select(UserLanguage).where(
            UserLanguage.id == user_language_id,
            UserLanguage.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not ul:
        raise HTTPException(404, "Nie znaleziono.")
    study_ids = select(StudySession.id).where(
        StudySession.user_id == user.id,
        StudySession.language_id == ul.language_id,
    )
    # Delete snapshots before their parent sessions, in the same transaction.
    await db.execute(delete(WordReview).where(
        WordReview.user_id == user.id, WordReview.language_id == ul.language_id,
    ))
    await db.execute(delete(StudyAnswer).where(StudyAnswer.session_id.in_(study_ids)))
    await db.execute(delete(StudySession).where(
        StudySession.user_id == user.id, StudySession.language_id == ul.language_id,
    ))
    await db.execute(delete(UserWord).where(
        UserWord.user_id == user.id, UserWord.language_id == ul.language_id,
    ))
    language = await db.get(Language, ul.language_id)
    if language:
        await db.execute(delete(Progress).where(
            Progress.user_id == user.id, Progress.language == language.code,
        ))
    await db.delete(ul)
    await db.commit()
    return {"ok": True}


@router.get("/user/languages/{language_id}/words")
async def list_words(
    language_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Lista słów użytkownika w danym języku."""
    # Sprawdź, że język jest dodany do profilu
    ul = (await db.execute(
        select(UserLanguage).where(
            UserLanguage.user_id == user.id,
            UserLanguage.language_id == language_id,
        )
    )).scalar_one_or_none()
    if not ul:
        raise HTTPException(404, "Ten język nie jest dodany do Twojego profilu.")

    lang = (await db.execute(
        select(Language).where(Language.id == language_id)
    )).scalar_one_or_none()

    words = (await db.execute(
        select(UserWord).where(
            UserWord.user_id == user.id,
            UserWord.language_id == language_id,
        ).order_by(UserWord.created_at.desc())
    )).scalars().all()

    return {
        "language": {
            "id": lang.id, "code": lang.code,
            "name_pl": lang.name_pl, "name_native": lang.name_native,
            "flag": lang.flag_emoji,
        },
        "words": [
            {
                "id": w.id,
                "word": w.word,
                "translation_pl": w.translation_pl,
                "translation_alternatives": w.translation_alternatives,
                "word_alternatives": w.word_alternatives,
                "is_valid": w.is_valid,
                "created_at": w.created_at.isoformat(),
            }
            for w in words
        ],
    }


@router.post("/user/languages/{language_id}/words")
async def add_word(
    language_id: int,
    payload: AddWordRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dodaj słowo, niezależnie od dostępności zewnętrznych słowników.
    Potwierdzenie może pochodzić wyłącznie z gotowego wyniku w cache serwera.
    """
    word = clean_text(payload.word)
    translation = clean_text(payload.translation_pl)

    await lock_vocabulary(db, user.id, language_id)

    if await duplicate_word(db, user.id, language_id, word):
        raise HTTPException(409, "To słowo już istnieje w tym języku.")

    w = UserWord(
        user_id=user.id,
        language_id=language_id,
        word=word,
        translation_pl=translation,
        translation_alternatives=accepted_variants(translation, payload.translation_alternatives)[1:],
        word_alternatives=accepted_variants(word, payload.word_alternatives)[1:],
        is_valid=await cached_confirmation(db, language_id, word),
    )
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return {
        "ok": True,
        "word": word_response(w),
    }


@router.post("/user/languages/{language_id}/words/import")
async def import_words(
    language_id: int,
    payload: ImportWordsRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import up to 100 pairs atomically; identical pairs are safe to retry.

    Quick entry never waits for external dictionary verification. Existing aliases,
    spelling, verification flags and review state are preserved on duplicates.
    Conflicting translations reject the entire batch without overwriting data.
    """
    await lock_vocabulary(db, user.id, language_id)
    language = await db.get(Language, language_id)
    existing = (await db.execute(select(UserWord).where(
        UserWord.user_id == user.id, UserWord.language_id == language_id,
    ))).scalars().all()
    by_word: dict[str, list[UserWord]] = {}
    for entry in existing:
        by_word.setdefault(normalize_answer(entry.word), []).append(entry)

    added, skipped, selected = [], 0, {}
    for index, entry in enumerate(payload.words, start=1):
        word, translation = clean_text(entry.word), clean_text(entry.translation_pl)
        # WordText rejects blanks before normalization; enforce again for callers
        # whose whitespace becomes empty after clean_text.
        if not word or not translation:
            raise HTTPException(422, f"Pozycja {index}: uzupełnij słowo i tłumaczenie.")
        key = normalize_answer(word)
        candidates = by_word.get(key, [])
        if candidates:
            if any(normalize_answer(item.translation_pl) != normalize_answer(translation) for item in candidates):
                raise HTTPException(409, f"Pozycja {index}: słowo „{word}” ma już inne tłumaczenie. Popraw listę lub użyj Edytuj. Nie zapisano żadnych nowych słów.")
            skipped += 1
            selected[key] = candidates[0]
            continue
        item = UserWord(
            user_id=user.id, language_id=language_id, word=word,
            translation_pl=translation, translation_alternatives=[],
            word_alternatives=[], is_valid=bool(language and dictionary.confirmed(language.code, word)),
        )
        by_word[key] = [item]
        selected[key] = item
        added.append(item)

    db.add_all(added)
    await db.commit()
    return {"ok": True, "added": len(added), "skipped": skipped,
            "words": [word_response(word) for word in selected.values()]}


def word_response(word: UserWord):
    return {
        "id": word.id, "word": word.word, "translation_pl": word.translation_pl,
        "translation_alternatives": word.translation_alternatives,
        "word_alternatives": word.word_alternatives, "is_valid": word.is_valid,
    }


@router.put("/words/{word_id}")
async def update_word(
    word_id: int,
    payload: AddWordRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    word = (await db.execute(select(UserWord).where(
        UserWord.id == word_id, UserWord.user_id == user.id,
    ))).scalar_one_or_none()
    if not word:
        raise HTTPException(404, "Nie znaleziono słowa.")
    await lock_vocabulary(db, user.id, word.language_id)
    await db.refresh(word)
    primary = clean_text(payload.word)
    if await duplicate_word(db, user.id, word.language_id, primary, exclude_id=word.id):
        raise HTTPException(409, "To słowo już istnieje w tym języku.")
    previous_signature = word_signature(word)
    verified = word.is_valid if word.word == primary else False
    word.word = primary
    word.translation_pl = clean_text(payload.translation_pl)
    word.translation_alternatives = accepted_variants(word.translation_pl, payload.translation_alternatives)[1:]
    word.word_alternatives = accepted_variants(word.word, payload.word_alternatives)[1:]
    word.is_valid = verified or await cached_confirmation(db, word.language_id, primary)
    if word_signature(word) != previous_signature:
        await db.execute(delete(WordReview).where(
            WordReview.user_id == user.id, WordReview.word_id == word.id,
        ))
    await db.commit()
    return {"ok": True, "word": word_response(word)}


@router.delete("/words/{word_id}")
async def delete_word(
    word_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    w = (await db.execute(
        select(UserWord).where(
            UserWord.id == word_id,
            UserWord.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Nie znaleziono słowa.")
    await db.execute(delete(WordReview).where(
        WordReview.user_id == user.id, WordReview.word_id == w.id,
    ))
    await db.delete(w)
    await db.commit()
    return {"ok": True}
