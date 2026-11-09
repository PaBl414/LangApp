"""
Sesje nauki: start, submit, historia.
"""
import random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import (
    User, UserLanguage, UserWord,
    StudySession, StudyAnswer, Language,
)
from .learning import current_user
from ..schemas import StudyStartRequest, StudySubmitRequest

router = APIRouter(prefix="/api/study", tags=["study"])

VALID_MODES = {"lang_to_pl", "pl_to_lang", "mix"}
MIN_WORDS = 4          # minimum słów, żeby quiz miał sens
MAX_WORDS = 50


@router.post("/start")
async def start_study(
    payload: StudyStartRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Body: {"language_id": 1, "mode": "lang_to_pl", "count": 10}
    Zwraca sesję + listę pytań (bez odpowiedzi).
    """
    lang_id = payload.language_id
    mode = payload.mode
    count = payload.count

    # czy język jest w profilu?
    ul = (await db.execute(
        select(UserLanguage).where(
            UserLanguage.user_id == user.id,
            UserLanguage.language_id == lang_id,
        )
    )).scalar_one_or_none()
    if not ul:
        raise HTTPException(404, "Ten język nie jest dodany do Twojego profilu.")

    # pobierz słowa
    words = (await db.execute(
        select(UserWord).where(
            UserWord.user_id == user.id,
            UserWord.language_id == lang_id,
        )
    )).scalars().all()

    if len(words) < MIN_WORDS:
        raise HTTPException(400, f"Potrzebujesz co najmniej {MIN_WORDS} słów, żeby rozpocząć naukę.")

    count = min(count, len(words))
    chosen = random.sample(words, count)

    # kierunek dla każdego pytania
    questions = []
    for w in chosen:
        if mode == "mix":
            direction = random.choice(["lang_to_pl", "pl_to_lang"])
        else:
            direction = mode

        if direction == "lang_to_pl":
            prompt = w.word
            expected = w.translation_pl
        else:
            prompt = w.translation_pl
            expected = w.word

        questions.append({
            "word_id": w.id,
            "direction": direction,
            "prompt": prompt,
            "expected": expected,   # wysyłamy do frontu tylko po to, by sprawdzić lokalnie?
        })

    # UWAGA: nie chcemy wysyłać "expected" do klienta — inaczej można oszukać.
    # Tworzymy sesję i zapisujemy poprawne odpowiedzi po stronie serwera
    # w pamięci tymczasowej (dict) — patrz niżej: trzymamy je w sesji DB.
    #
    # Prościej: zapisujemy "oczekiwane" w bazie od razu jako StudyAnswer z given=""
    # i is_correct=False; przy submit aktualizujemy.

    session = StudySession(
        user_id=user.id,
        language_id=lang_id,
        mode=mode,
        total=count,
        correct=0,
        finished=False,
    )
    db.add(session)
    await db.flush()  # żeby mieć session.id

    # Zapisz "szkielet" odpowiedzi z oczekiwanymi wartościami
    for q in questions:
        db.add(StudyAnswer(
            session_id=session.id,
            word_id=q["word_id"],
            prompt=q["prompt"],
            expected=q["expected"],
            given="",
            is_correct=False,
            direction=q["direction"],
        ))
    await db.commit()
    await db.refresh(session)

    # Do klienta wysyłamy tylko prompt + id — bez "expected"
    public_questions = [
        {"word_id": q["word_id"], "direction": q["direction"], "prompt": q["prompt"]}
        for q in questions
    ]

    return {
        "session_id": session.id,
        "mode": mode,
        "total": count,
        "questions": public_questions,
    }


@router.post("/submit")
async def submit_study(
    payload: StudySubmitRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Body: {
      "session_id": 1,
      "answers": [
        {"word_id": 3, "given": "hello"},
        ...
      ]
    }
    Sprawdza odpowiedzi (case-insensitive, trim), zapisuje, zwraca wynik.
    """
    session_id = payload.session_id
    answers = payload.answers

    session = (await db.execute(
        select(StudySession).where(
            StudySession.id == session_id,
            StudySession.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Sesja nie istnieje.")
    if session.finished:
        raise HTTPException(400, "Ta sesja została już zakończona.")

    # Pobierz wszystkie StudyAnswer dla sesji
    db_answers = (await db.execute(
        select(StudyAnswer).where(StudyAnswer.session_id == session.id)
    )).scalars().all()
    by_word = {a.word_id: a for a in db_answers}

    given_map = {answer.word_id: answer.given.strip() for answer in answers}
    if given_map.keys() - by_word.keys():
        raise HTTPException(400, "Odpowiedź dotyczy słowa spoza tej sesji.")

    correct_count = 0
    results = []
    for a in db_answers:
        given = given_map.get(a.word_id, "")
        ok = _normalize(given) == _normalize(a.expected)
        a.given = given
        a.is_correct = ok
        if ok:
            correct_count += 1
        results.append({
            "word_id": a.word_id,
            "prompt": a.prompt,
            "expected": a.expected,
            "given": given,
            "is_correct": ok,
            "direction": a.direction,
        })

    session.correct = correct_count
    session.finished = True
    session.finished_at = datetime.utcnow()
    await db.commit()

    return {
        "session_id": session.id,
        "total": session.total,
        "correct": correct_count,
        "percent": round(correct_count / session.total * 100) if session.total else 0,
        "results": results,
    }


def _normalize(s: str) -> str:
    return (s or "").strip().lower().replace("  ", " ")


@router.get("/history")
async def study_history(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ostatnie 20 sesji użytkownika."""
    rows = (await db.execute(
        select(StudySession)
        .where(StudySession.user_id == user.id, StudySession.finished == True)
        .order_by(StudySession.finished_at.desc())
        .limit(20)
    )).scalars().all()

    # Pobierz języki dla czytelnego wyświetlenia
    lang_ids = {r.language_id for r in rows}
    lang_map = {}
    if lang_ids:
        langs = (await db.execute(
            select(Language).where(Language.id.in_(lang_ids))
        )).scalars().all()
        lang_map = {l.id: l for l in langs}

    return [
        {
            "id": r.id,
            "language": {
                "id": lang_map[r.language_id].id,
                "name_pl": lang_map[r.language_id].name_pl,
                "flag": lang_map[r.language_id].flag_emoji,
            } if r.language_id in lang_map else None,
            "mode": r.mode,
            "total": r.total,
            "correct": r.correct,
            "percent": round(r.correct / r.total * 100) if r.total else 0,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        }
        for r in rows
    ]
