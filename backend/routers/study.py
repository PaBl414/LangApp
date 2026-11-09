"""Owned, resumable quizzes with versioned drafts and immutable final results."""
import random

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..grading import accepted_variants, is_correct, normalize_answer
from ..models import Language, StudyAnswer, StudySession, User, UserLanguage, UserWord, WordReview
from ..reviews import record_reviews
from ..time_utils import learning_date, utc_now
from ..schemas import StudyDraftRequest, StudyStartRequest, StudySubmitRequest
from .learning import current_user

router = APIRouter(prefix="/api/study", tags=["study"])
MIN_WORDS = 4
CONFLICT = "Quiz zmienił się w innej karcie. Wczytaj aktualny zapis przed kontynuowaniem."


async def owned_session(db: AsyncSession, session_id: int, user_id: int) -> StudySession:
    session = (await db.execute(select(StudySession).where(
        StudySession.id == session_id, StudySession.user_id == user_id,
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    if session is None:
        raise HTTPException(404, "Sesja nie istnieje.")
    return session


async def session_answers(db: AsyncSession, session_id: int) -> list[StudyAnswer]:
    return list((await db.execute(select(StudyAnswer).where(
        StudyAnswer.session_id == session_id,
    ).order_by(StudyAnswer.id).execution_options(populate_existing=True))).scalars().all())


def result_response(session: StudySession, answers: list[StudyAnswer]) -> dict:
    return {
        "session_id": session.id, "total": session.total, "correct": session.correct,
        "percent": round(session.correct / session.total * 100) if session.total else 0,
        "results": [{
            "word_id": answer.word_id, "prompt": answer.prompt,
            "expected": answer.expected,
            "accepted_answers": accepted_variants(answer.expected, answer.accepted_answers),
            "given": answer.given, "is_correct": answer.is_correct, "direction": answer.direction,
        } for answer in answers],
    }


def session_response(session: StudySession, answers: list[StudyAnswer]) -> dict:
    response = {
        "session_id": session.id, "language_id": session.language_id, "source": session.source,
        "mode": session.mode, "total": session.total, "revision": session.revision,
        "current_index": session.current_index, "finished": session.finished,
        "questions": [{"word_id": answer.word_id, "direction": answer.direction, "prompt": answer.prompt} for answer in answers],
        "answers": [{"word_id": answer.word_id, "given": answer.given} for answer in answers],
    }
    # Expected answers and grading are never exposed for an unfinished quiz.
    if session.finished:
        response["result"] = result_response(session, answers)
    return response


def given_map(payload, answers: list[StudyAnswer]) -> dict[int, str]:
    given = {answer.word_id: answer.given for answer in payload.answers}
    if given.keys() - {answer.word_id for answer in answers}:
        raise HTTPException(400, "Odpowiedź dotyczy słowa spoza tej sesji.")
    return given


@router.post("/start")
async def start_study(
    payload: StudyStartRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id
    request_id = str(payload.request_id) if payload.request_id else None

    async def existing_request():
        if request_id is None:
            return None
        session = (await db.execute(select(StudySession).where(
            StudySession.user_id == user_id, StudySession.start_request_id == request_id,
        ))).scalar_one_or_none()
        if session:
            if (session.language_id, session.mode, session.requested_count, session.source) != (payload.language_id, payload.mode, payload.count, payload.source):
                raise HTTPException(409, "Identyfikator rozpoczęcia został już użyty dla innych ustawień.")
            return session_response(session, await session_answers(db, session.id))
        return None

    existing = await existing_request()
    if existing is not None:
        return existing
    membership = (await db.execute(select(UserLanguage.id).where(
        UserLanguage.user_id == user_id, UserLanguage.language_id == payload.language_id,
    ))).scalar_one_or_none()
    if membership is None:
        raise HTTPException(404, "Ten język nie jest dodany do Twojego profilu.")
    query = select(UserWord).where(
        UserWord.user_id == user_id, UserWord.language_id == payload.language_id,
    )
    if payload.source == "due":
        query = query.join(WordReview, WordReview.word_id == UserWord.id).where(
            WordReview.user_id == user_id, WordReview.direction == payload.mode,
            WordReview.due_on <= learning_date(utc_now()),
        ).order_by(WordReview.due_on, WordReview.last_correct, WordReview.last_reviewed_at, UserWord.id).limit(payload.count)
    words = list((await db.execute(query)).scalars().all())
    if payload.source == "due" and not words:
        raise HTTPException(400, "Brak zaplanowanych powtórek w tym kierunku na dziś.")
    if payload.source == "all" and len(words) < MIN_WORDS:
        raise HTTPException(400, f"Potrzebujesz co najmniej {MIN_WORDS} słów, żeby rozpocząć naukę.")
    chosen = words if payload.source == "due" else random.sample(words, min(payload.count, len(words)))
    session = StudySession(
        user_id=user_id, language_id=payload.language_id, mode=payload.mode,
        total=len(chosen), requested_count=payload.count, start_request_id=request_id, source=payload.source,
    )
    db.add(session)
    try:
        await db.flush()
        answers = []
        for word in chosen:
            direction = random.choice(["lang_to_pl", "pl_to_lang"]) if payload.mode == "mix" else payload.mode
            to_polish = direction == "lang_to_pl"
            expected = word.translation_pl if to_polish else word.word
            variants = word.translation_alternatives if to_polish else word.word_alternatives
            answer = StudyAnswer(
                session_id=session.id, word_id=word.id, direction=direction,
                prompt=word.word if to_polish else word.translation_pl,
                expected=expected, accepted_answers=accepted_variants(expected, variants),
                given="", is_correct=False,
            )
            answers.append(answer)
            db.add(answer)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await existing_request()
        if existing is not None:
            return existing
        raise
    return session_response(session, answers)


@router.get("/active")
async def active_studies(
    language_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = (await db.execute(select(StudySession).where(
        StudySession.user_id == user.id, StudySession.language_id == language_id,
        StudySession.finished.is_(False),
    ).order_by(StudySession.id.desc()).limit(20))).scalars().all()
    return {"sessions": [{
        "session_id": session.id, "mode": session.mode, "total": session.total, "source": session.source,
        "current_index": session.current_index, "created_at": session.created_at.isoformat(),
    } for session in sessions]}


@router.get("/sessions/{session_id}")
async def get_study(
    session_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await owned_session(db, session_id, user.id)
    return session_response(session, await session_answers(db, session.id))


@router.put("/sessions/{session_id}/draft")
async def save_draft(
    session_id: int,
    payload: StudyDraftRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = user.id
    session = await owned_session(db, session_id, user_id)
    answers = await session_answers(db, session_id)
    given = given_map(payload, answers)

    def same_draft():
        return session.current_index == payload.current_index and all(
            answer.given == given[answer.word_id] for answer in answers if answer.word_id in given
        )

    if session.finished:
        raise HTTPException(409, "Quiz jest już zakończony. Wczytaj zapisany wynik.")
    if payload.current_index >= session.total:
        raise HTTPException(400, "Nieprawidłowy numer pytania.")
    if same_draft():
        return session_response(session, answers)
    if session.revision != payload.revision:
        raise HTTPException(409, CONFLICT)
    claim = await db.execute(update(StudySession).where(
        StudySession.id == session_id, StudySession.user_id == user_id,
        StudySession.finished.is_(False), StudySession.revision == payload.revision,
    ).values(revision=payload.revision + 1, current_index=payload.current_index).execution_options(synchronize_session=False))
    if claim.rowcount != 1:
        await db.rollback()
        session = await owned_session(db, session_id, user_id)
        answers = await session_answers(db, session_id)
        if not session.finished and same_draft():
            return session_response(session, answers)
        raise HTTPException(409, CONFLICT)
    for answer in answers:
        if answer.word_id in given:
            answer.given = given[answer.word_id]
    await db.commit()
    await db.refresh(session)
    return session_response(session, answers)


@router.post("/submit")
async def submit_study(
    payload: StudySubmitRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id, session_id = user.id, payload.session_id
    session = await owned_session(db, session_id, user_id)
    answers = await session_answers(db, session_id)
    if session.finished:
        return result_response(session, answers)
    given = given_map(payload, answers)
    if payload.revision is not None and session.revision != payload.revision:
        raise HTTPException(409, CONFLICT)
    revision = session.revision
    graded = [(answer, given.get(answer.word_id, answer.given)) for answer in answers]
    correct = sum(is_correct(value, answer.expected, answer.accepted_answers) for answer, value in graded)
    completed_at = utc_now()
    claim = await db.execute(update(StudySession).where(
        StudySession.id == session_id, StudySession.user_id == user_id,
        StudySession.finished.is_(False), StudySession.revision == revision,
    ).values(
        revision=revision + 1, correct=correct, finished=True, current_index=session.total,
        finished_at=completed_at,
    ).execution_options(synchronize_session=False))
    if claim.rowcount != 1:
        await db.rollback()
        session = await owned_session(db, session_id, user_id)
        if session.finished:
            return result_response(session, await session_answers(db, session_id))
        raise HTTPException(409, CONFLICT)
    for answer, value in graded:
        answer.given = value
        answer.is_correct = is_correct(value, answer.expected, answer.accepted_answers)
    await record_reviews(db, session, answers, completed_at)
    await db.commit()
    await db.refresh(session)
    return result_response(session, answers)


# Kept for callers of the former normalization helper.
_normalize = normalize_answer


@router.get("/history")
async def study_history(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    sessions = (await db.execute(select(StudySession).where(
        StudySession.user_id == user.id, StudySession.finished.is_(True),
    ).order_by(StudySession.finished_at.desc(), StudySession.id.desc()).limit(20))).scalars().all()
    language_ids = {session.language_id for session in sessions}
    languages = (await db.execute(select(Language).where(Language.id.in_(language_ids)))).scalars().all() if language_ids else []
    language_map = {language.id: language for language in languages}
    return [{
        "id": session.id,
        "language": {"id": language.id, "name_pl": language.name_pl, "flag": language.flag_emoji} if (language := language_map.get(session.language_id)) else None,
        "mode": session.mode, "total": session.total, "correct": session.correct,
        "percent": round(session.correct / session.total * 100) if session.total else 0,
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
    } for session in sessions]
