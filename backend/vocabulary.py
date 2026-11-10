"""Recycle-bin retention. Historical quiz snapshots are never removed here."""
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import UserWord, WordReview
from .time_utils import utc_now

TRASH_RETENTION = timedelta(days=7)


async def purge_expired_words(db: AsyncSession, user_id: int) -> int:
    conditions = (UserWord.user_id == user_id, UserWord.deleted_at <= utc_now() - TRASH_RETENTION)
    if (await db.execute(select(UserWord.id).where(*conditions).limit(1))).scalar_one_or_none() is None:
        return 0
    expired_ids = select(UserWord.id).where(*conditions)
    await db.execute(delete(WordReview).where(WordReview.user_id == user_id, WordReview.word_id.in_(expired_ids)))
    result = await db.execute(delete(UserWord).where(*conditions))
    return result.rowcount
