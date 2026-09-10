"""
Endpointy: lista języków, języki użytkownika.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Language, UserLanguage
from .learning import current_user
from ..models import User

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
    payload: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dodaj język do profilu użytkownika. Body: {"language_id": 3}"""
    lang_id = payload.get("language_id")
    if not isinstance(lang_id, int):
        raise HTTPException(400, "Brak language_id.")

    lang = (await db.execute(select(Language).where(Language.id == lang_id))).scalar_one_or_none()
    if not lang:
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
    await db.commit()
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
    await db.delete(ul)
    await db.commit()
    return {"ok": True}
from ..models import UserWord
from ..models import Language as LanguageModel


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
        select(LanguageModel).where(LanguageModel.id == language_id)
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
                "is_valid": w.is_valid,
                "created_at": w.created_at.isoformat(),
            }
            for w in words
        ],
    }


@router.post("/user/languages/{language_id}/words")
async def add_word(
    language_id: int,
    payload: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dodaj słowo. Body: {"word": "...", "translation_pl": "...", "is_valid": true/false}
    """
    word = (payload.get("word") or "").strip()
    translation = (payload.get("translation_pl") or "").strip()
    is_valid = bool(payload.get("is_valid", True))

    if not word or not translation:
        raise HTTPException(400, "Słowo i tłumaczenie nie mogą być puste.")
    if len(word) > 128 or len(translation) > 128:
        raise HTTPException(400, "Słowo/tłumaczenie za długie (max 128 znaków).")

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
        is_valid=is_valid,
    )
    db.add(w)
    await db.commit()
    await db.refresh(w)
    return {
        "ok": True,
        "word": {
            "id": w.id, "word": w.word,
            "translation_pl": w.translation_pl, "is_valid": w.is_valid,
        },
    }


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
    await db.delete(w)
    await db.commit()
    return {"ok": True}