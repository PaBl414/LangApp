"""
Endpointy: lista języków, języki użytkownika.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Language, UserLanguage, User, UserWord, StudySession, StudyAnswer, Progress, WordReview
from ..schemas import AddLanguageRequest, AddWordRequest
from ..grading import accepted_variants, clean_text
from ..reviews import word_signature
from .learning import current_user

router = APIRouter(prefix="/api", tags=["languages"])


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
    Dodaj słowo. Body: {"word": "...", "translation_pl": "...", "is_valid": true/false}
    """
    word = clean_text(payload.word)
    translation = clean_text(payload.translation_pl)
    is_valid = payload.is_valid

    ul = (await db.execute(
        select(UserLanguage).where(
            UserLanguage.user_id == user.id,
            UserLanguage.language_id == language_id,
        )
    )).scalar_one_or_none()
    if not ul:
        raise HTTPException(404, "Ten język nie jest dodany do Twojego profilu.")

    # Unikalność: to samo słowo w tym samym języku u tego samego użytkownika
    existing = (await db.execute(
        select(UserWord).where(
            UserWord.user_id == user.id,
            UserWord.language_id == language_id,
            UserWord.word == word,
        )
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "To słowo już istnieje w tym języku.")

    w = UserWord(
        user_id=user.id,
        language_id=language_id,
        word=word,
        translation_pl=translation,
        translation_alternatives=accepted_variants(translation, payload.translation_alternatives)[1:],
        word_alternatives=accepted_variants(word, payload.word_alternatives)[1:],
        is_valid=is_valid,
    )
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return {
        "ok": True,
        "word": word_response(w),
    }


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
    primary = clean_text(payload.word)
    duplicate = (await db.execute(select(UserWord.id).where(
        UserWord.user_id == user.id, UserWord.language_id == word.language_id,
        UserWord.word == primary, UserWord.id != word.id,
    ).limit(1))).scalar_one_or_none()
    if duplicate:
        raise HTTPException(409, "To słowo już istnieje w tym języku.")
    previous_signature = word_signature(word)
    word.word = primary
    word.translation_pl = clean_text(payload.translation_pl)
    word.translation_alternatives = accepted_variants(word.translation_pl, payload.translation_alternatives)[1:]
    word.word_alternatives = accepted_variants(word.word, payload.word_alternatives)[1:]
    word.is_valid = payload.is_valid
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
