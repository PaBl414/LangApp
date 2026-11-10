"""Deterministic daily review schedule, version 1.

Updates run inside the transaction that first finalizes a quiz. Retrying a
completed quiz never reaches this function and cannot award another attempt.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .grading import accepted_variants, normalize_answer
from .models import StudyAnswer, StudySession, UserWord, WordReview
from .time_utils import learning_date

INTERVAL_DAYS = (1, 3, 7, 14, 30, 60)


def next_review(consecutive_correct: int, correct: bool, when: datetime):
    streak = consecutive_correct + 1 if correct else 0
    interval = INTERVAL_DAYS[min(streak - 1, len(INTERVAL_DAYS) - 1)] if correct else 0
    return streak, learning_date(when) + timedelta(days=interval)


def snapshot_matches(word: UserWord, answer: StudyAnswer) -> bool:
    to_polish = answer.direction == "lang_to_pl"
    prompt = word.word if to_polish else word.translation_pl
    expected = word.translation_pl if to_polish else word.word
    alternatives = word.translation_alternatives if to_polish else word.word_alternatives
    current = {normalize_answer(value) for value in accepted_variants(expected, alternatives)}
    snapshot = {normalize_answer(value) for value in accepted_variants(answer.expected, answer.accepted_answers)}
    return normalize_answer(prompt) == normalize_answer(answer.prompt) and current == snapshot


def word_signature(word: UserWord):
    return (
        normalize_answer(word.word), normalize_answer(word.translation_pl),
        frozenset(normalize_answer(value) for value in word.word_alternatives),
        frozenset(normalize_answer(value) for value in word.translation_alternatives),
    )


async def record_reviews(db: AsyncSession, session: StudySession, answers: list[StudyAnswer], when: datetime):
    words = (await db.execute(select(UserWord).where(
        UserWord.user_id == session.user_id, UserWord.language_id == session.language_id,
        UserWord.deleted_at.is_(None),
        UserWord.id.in_([answer.word_id for answer in answers]),
    ))).scalars().all()
    by_id = {word.id: word for word in words}
    for answer in answers:
        word = by_id.get(answer.word_id)
        # Deleted/edited entries must not receive learning credit for an old snapshot.
        if (word is None or not snapshot_matches(word, answer)
                or (word.created_at and session.created_at and word.created_at > session.created_at)):
            continue
        query = select(WordReview).where(
            WordReview.user_id == session.user_id, WordReview.word_id == word.id,
            WordReview.direction == answer.direction,
        ).with_for_update()
        review = (await db.execute(query)).scalar_one_or_none()
        if review is None:
            try:
                async with db.begin_nested():
                    review = WordReview(
                        user_id=session.user_id, word_id=word.id, language_id=word.language_id,
                        direction=answer.direction, attempts=0, correct_answers=0,
                        consecutive_correct=0, due_on=learning_date(when),
                        last_correct=answer.is_correct, last_reviewed_at=when,
                    )
                    db.add(review)
                    await db.flush()
            except IntegrityError:
                review = (await db.execute(query)).scalar_one()
        reviewed_at = max(when, review.last_reviewed_at)
        review.consecutive_correct, review.due_on = next_review(review.consecutive_correct, answer.is_correct, reviewed_at)
        review.attempts += 1
        review.correct_answers += int(answer.is_correct)
        review.last_correct = answer.is_correct
        review.last_reviewed_at = reviewed_at
