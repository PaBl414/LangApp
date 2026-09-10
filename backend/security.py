"""
Hashowanie haseł (bcrypt z losową solą) oraz tokeny sesji.
"""
import secrets
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain: str) -> str:
    # bcrypt automatycznie generuje losową sól dla każdego hasła
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def new_cookie_id() -> str:
    return secrets.token_urlsafe(24)