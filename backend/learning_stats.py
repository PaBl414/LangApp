"""Read-only learning statistics; drafts never count as completed practice."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Language, StudySession, UserLanguage, UserWord, WordReview
from .time_utils import LEARNING_TIMEZONE, learning_date


def current_streak(days: set[date], today: date) -> int:
    last = today if today in days else today - timedelta(days=1)
    streak = 0
    while last in days:
        streak += 1
        last -= timedelta(days=1)
    return streak


def accuracy(correct: int, attempts: int):
    return round(correct / attempts * 100) if attempts else None


async def statistics(db: AsyncSession, user_id: int, when: datetime):
    today = learning_date(when)
    languages = (await db.execute(select(Language, UserLanguage.id).join(
        UserLanguage, UserLanguage.language_id == Language.id,
    ).where(UserLanguage.user_id == user_id).order_by(Language.name_pl))).all()
    totals = {row.language_id: row.word_count for row in (await db.execute(select(
        UserWord.language_id, func.count().label("word_count"),
    ).where(UserWord.user_id == user_id).group_by(UserWord.language_id))).all()}
    practiced = {row.language_id: row.word_count for row in (await db.execute(select(
        WordReview.language_id, func.count(func.distinct(WordReview.word_id)).label("word_count"),
    ).join(UserWord, and_(UserWord.id == WordReview.word_id, UserWord.user_id == WordReview.user_id)).where(
        WordReview.user_id == user_id, WordReview.attempts > 0, WordReview.language_id == UserWord.language_id,
    ).group_by(WordReview.language_id))).all()}
    completed = defaultdict(lambda: {"quizzes": 0, "answers": 0, "correct": 0, "days": set()})
    all_days = set()
    stream = await db.stream(select(
        StudySession.language_id, StudySession.total, StudySession.correct, StudySession.finished_at,
    ).where(StudySession.user_id == user_id, StudySession.finished.is_(True)).execution_options(yield_per=500))
    try:
        async for row in stream:
            record = completed[row.language_id]
            record["quizzes"] += 1
            record["answers"] += row.total
            record["correct"] += row.correct
            if row.finished_at:
                day = learning_date(row.finished_at)
                record["days"].add(day)
                all_days.add(day)
    finally:
        await stream.close()
    progress = []
    for language, membership in languages:
        record = completed[language.id]
        progress.append({
            "id": language.id, "language": language.code, "name_pl": language.name_pl,
            "name_native": language.name_native, "flag": language.flag_emoji, "user_language_id": membership,
            "total_words": totals.get(language.id, 0), "practiced_words": practiced.get(language.id, 0),
            "quizzes": record["quizzes"], "answers": record["answers"], "correct": record["correct"],
            "accuracy": accuracy(record["correct"], record["answers"]),
            "xp": record["correct"] * 10, "streak": current_streak(record["days"], today),
        })
    answers = sum(record["answers"] for record in completed.values())
    correct = sum(record["correct"] for record in completed.values())
    summary = {
        "total_words": sum(totals.values()), "practiced_words": sum(practiced.values()),
        "quizzes": sum(record["quizzes"] for record in completed.values()),
        "answers": answers, "correct": correct, "accuracy": accuracy(correct, answers),
        "streak": current_streak(all_days, today), "xp": correct * 10,
    }
    return summary, progress


def owned_reviews(user_id: int):
    return and_(
        WordReview.user_id == user_id, UserWord.user_id == user_id,
        UserLanguage.user_id == user_id, UserLanguage.language_id == UserWord.language_id,
    )


async def due_groups(db: AsyncSession, user_id: int, today: date):
    rows = (await db.execute(select(
        Language.id, Language.name_pl, Language.flag_emoji, WordReview.direction,
        func.count().label("review_count"), func.min(WordReview.due_on).label("oldest_due"),
    ).select_from(WordReview).join(UserWord, UserWord.id == WordReview.word_id).join(
        UserLanguage, and_(UserLanguage.user_id == WordReview.user_id, UserLanguage.language_id == WordReview.language_id),
    ).join(Language, Language.id == WordReview.language_id).where(
        owned_reviews(user_id), WordReview.due_on <= today,
    ).group_by(Language.id, Language.name_pl, Language.flag_emoji, WordReview.direction).order_by(Language.name_pl, WordReview.direction))).all()
    return [{"language_id": row.id, "name_pl": row.name_pl, "flag": row.flag_emoji,
             "direction": row.direction, "count": row.review_count, "oldest_due": row.oldest_due.isoformat()} for row in rows]


async def difficult_words(db: AsyncSession, user_id: int):
    attempts = func.sum(WordReview.attempts)
    correct = func.sum(WordReview.correct_answers)
    last_error = func.max(case((WordReview.last_correct.is_(False), 1), else_=0))
    ratio = correct * 1.0 / func.nullif(attempts, 0)
    rows = (await db.execute(select(
        UserWord.id, UserWord.word, UserWord.translation_pl, UserWord.language_id,
        Language.name_pl, attempts.label("attempts"), correct.label("correct"),
        func.min(WordReview.due_on).label("due_on"),
    ).select_from(WordReview).join(UserWord, UserWord.id == WordReview.word_id).join(
        UserLanguage, and_(UserLanguage.user_id == WordReview.user_id, UserLanguage.language_id == WordReview.language_id),
    ).join(Language, Language.id == WordReview.language_id).where(owned_reviews(user_id)).group_by(
        UserWord.id, UserWord.word, UserWord.translation_pl, UserWord.language_id, Language.name_pl,
    ).having(attempts > correct, (last_error == 1) | (ratio < 0.8)).order_by(
        last_error.desc(), ratio, attempts.desc(), UserWord.id,
    ).limit(10))).all()
    return [{"word_id": row.id, "word": row.word, "translation_pl": row.translation_pl,
             "language_id": row.language_id, "language_name": row.name_pl,
             "attempts": row.attempts, "correct": row.correct, "accuracy": accuracy(row.correct, row.attempts),
             "due_on": row.due_on.isoformat()} for row in rows]


async def history_page(db: AsyncSession, user_id: int, limit: int = 10, offset: int = 0):
    conditions = (StudySession.user_id == user_id, StudySession.finished.is_(True))
    total = await db.scalar(select(func.count()).select_from(StudySession).where(*conditions))
    rows = (await db.execute(select(StudySession, Language).outerjoin(
        Language, Language.id == StudySession.language_id,
    ).where(*conditions).order_by(StudySession.finished_at.desc(), StudySession.id.desc()).limit(limit).offset(offset))).all()
    items = [{
        "id": session.id, "language_id": session.language_id,
        "language_name": language.name_pl if language else "Usunięty język",
        "mode": session.mode, "source": session.source, "total": session.total, "correct": session.correct,
        "percent": accuracy(session.correct, session.total),
        "finished_at": session.finished_at.isoformat() + "Z" if session.finished_at else None,
    } for session, language in rows]
    next_offset = offset + len(items)
    return {"items": items, "total": total, "next_offset": next_offset if next_offset < total else None}


async def dashboard(db: AsyncSession, user_id: int, when: datetime):
    summary, languages = await statistics(db, user_id, when)
    today = learning_date(when)
    due = await due_groups(db, user_id, today)
    summary["due_reviews"] = sum(group["count"] for group in due)
    active = (await db.execute(select(StudySession).join(UserLanguage, and_(
        UserLanguage.user_id == StudySession.user_id, UserLanguage.language_id == StudySession.language_id,
    )).where(StudySession.user_id == user_id, StudySession.finished.is_(False)).order_by(
        StudySession.id.desc(),
    ).limit(1))).scalar_one_or_none()
    return {
        "timezone": LEARNING_TIMEZONE, "today": today.isoformat(), "summary": summary,
        "languages": languages, "due": due, "difficult": await difficult_words(db, user_id),
        "history": await history_page(db, user_id),
        "active_session": {"session_id": active.id, "language_id": active.language_id,
                           "current_index": active.current_index, "total": active.total} if active else None,
    }
