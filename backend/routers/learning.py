"""
Endpointy chronione — dane użytkownika, postęp nauki.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Session as SessionModel, User, Progress
from ..sessions import COOKIE_NAME, session_cutoff

router = APIRouter(prefix="/api", tags=["learning"])


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Brak sesji.")
    s = (await db.execute(
        select(SessionModel).where(SessionModel.token == token)
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(401, "Sesja wygasła.")
    if s.created_at <= session_cutoff():
        await db.delete(s)
        await db.commit()
        raise HTTPException(401, "Sesja wygasła. Zaloguj się ponownie.")
    user = (await db.execute(
        select(User).where(User.id == s.user_id)
    )).scalar_one_or_none()
    if not user:
        await db.delete(s)
        await db.commit()
        raise HTTPException(401, "Użytkownik nie istnieje.")
    return user


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "login": user.login,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/progress")
async def progress(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Progress).where(Progress.user_id == user.id)
    )).scalars().all()
    return [{"language": r.language, "xp": r.xp, "streak": r.streak} for r in rows]
