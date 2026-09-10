"""
Endpointy rejestracji, logowania i wylogowania.
Wersja debug: loguje każde wejście, walidację i wynik.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import User, Session as SessionModel
from ..schemas import RegisterRequest, LoginRequest
from ..security import hash_password, verify_password, new_session_token
from ..antifraud import is_duplicate

log = logging.getLogger("langapp.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

COOKIE_NAME = "langapp_session"
COOKIE_ID_NAME = "langapp_cid"


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
    log.info("== REGISTER == login=%r ip=%s fp_len=%d cookie_len=%d",
             payload.login, ip, len(payload.fingerprint), len(payload.cookie_id))
    log.debug("   fingerprint=%r", payload.fingerprint[:80])
    log.debug("   cookie_id=%r", payload.cookie_id[:80])

    if payload.password != payload.password_confirm:
        log.warning("Hasła są różne")
        raise HTTPException(400, "Hasła nie są identyczne.")

    existing_login = await db.execute(select(User).where(User.login == payload.login))
    if existing_login.scalar_one_or_none():
        log.warning("   login już istnieje: %s", payload.login)
        raise HTTPException(409, "Taki login już istnieje.")

    dup = await is_duplicate(db, payload.cookie_id, payload.fingerprint, ip)
    log.info("   antifraud duplicate=%s", dup)
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
    await db.commit()
    await db.refresh(user)
    log.info("   UTWORZONO konto id=%s login=%s", user.id, user.login)

    response.set_cookie(
        COOKIE_ID_NAME, payload.cookie_id,
        max_age=60 * 60 * 24 * 365, httponly=False, samesite="lax",
    )
    return {"ok": True, "user": {"id": user.id, "login": user.login}}


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    log.info("== LOGIN == login=%r ip=%s", payload.login, client_ip(request))

    result = await db.execute(select(User).where(User.login == payload.login))
    user = result.scalar_one_or_none()

    if not user:
        log.warning("   nie ma takiego loginu")
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")

    if not verify_password(payload.password, user.password_hash):
        log.warning("   złe hasło dla %s", payload.login)
        raise HTTPException(401, "Nieprawidłowy login lub hasło.")

    user.fingerprint = payload.fingerprint
    user.cookie_id = payload.cookie_id
    user.ip_address = client_ip(request)
    user.last_login = datetime.utcnow()

    token = new_session_token()
    db.add(SessionModel(token=token, user_id=user.id))
    await db.commit()
    log.info("   ZALOGOWANO user_id=%s", user.id)

    response.set_cookie(COOKIE_NAME, token, max_age=60 * 60 * 24 * 7, httponly=True, samesite="lax")
    response.set_cookie(COOKIE_ID_NAME, payload.cookie_id, max_age=60 * 60 * 24 * 365, httponly=True, samesite="lax")
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
