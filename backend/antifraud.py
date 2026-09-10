"""
Wykrywanie multikont: blokujemy rejestrację tylko wtedy,
gdy cookie, fingerprint ORAZ IP są identyczne z istniejącym kontem.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import User


async def is_duplicate(
    db: AsyncSession, cookie_id: str, fingerprint: str, ip: str
) -> bool:
    stmt = select(User).where(
        User.cookie_id == cookie_id,
        User.fingerprint == fingerprint,
        User.ip_address == ip,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None