"""
Endpointy rejestracji, logowania i wylogowania.
Wersja debug: loguje każde wejście, walidację i wynik.
"""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, Session as SessionModel
from ..schemas import RegisterRequest, LoginRequest
from ..security import hash_password, verify_password, new_session_token
from ..antifraud import is_duplicate

router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "langapp_session"
COOKIE_ID_NAME = "langapp_cid"
COOKIE_SECURE = os.getenv("LANGAPP_COOKIE_SECURE", "0").lower() in {"1", "true", "yes"}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "0.0.0.0"


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    ip = client_ip(request)
    if payload.password != payload.password_confirm:
        raise HTTPException(400, "Hasła nie są identyczne.")

    existing_login = await db.execute(select(User).where(User.login == payload.login))
    if existing_login.scalar_one_or_none():
        raise HTTPException(409, "Taki login już istnieje.")

    dup = await is_duplicate(db, payload.cookie_id, payload.fingerprint, ip)
    if dup:
        raise HTTPException(
            status_code=403,
            detail="Wykryto próbę utworzenia multikonta. Rejestracja zablokowana.",
        )

    user = User(
        login=payload.login,
        password_hash=hash_password(payload.password),
        cookie_id=payload.cookie_id,
        fingerprint=payload.fingerprint,
        ip_address=ip,
    )
    db.add(user)
    await db.flush()
    token = new_session_token()
    db.add(SessionModel(token=token, user_id=user.id))
    await db.commit()
    await db.refresh(user)

    response.set_cookie(
        COOKIE_NAME, token, max_age=60 * 60 * 24 * 7,
        httponly=True, samesite="lax", secure=COOKIE_SECURE,
    )

    response.set_cookie(
        COOKIE_ID_NAME, payload.cookie_id,
        max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax",
        secure=COOKIE_SECURE,
    )
    return {"ok": True, "user": {"id": user.id, "login": user.login}}


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.login == payload.login))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")

    password_valid, upgraded_hash = verify_password(payload.password, user.password_hash)
    if not password_valid:
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")
    if upgraded_hash:
        user.password_hash = upgraded_hash

    user.fingerprint = payload.fingerprint
    user.cookie_id = payload.cookie_id
    user.ip_address = client_ip(request)
    user.last_login = datetime.utcnow()

    token = new_session_token()
    db.add(SessionModel(token=token, user_id=user.id))
    await db.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=60 * 60 * 24 * 7, httponly=True, samesite="lax", secure=COOKIE_SECURE)
    response.set_cookie(COOKIE_ID_NAME, payload.cookie_id, max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax", secure=COOKIE_SECURE)
    return {"ok": True, "user": {"id": user.id, "login": user.login}}


@router.post("/logout")
async def logout(response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        result = await db.execute(select(SessionModel).where(SessionModel.token == token))
        s = result.scalar_one_or_none()
        if s:
            await db.delete(s)
            await db.commit()
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}
