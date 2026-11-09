"""
Hashowanie haseł (Argon2, weryfikacja dawnych hashy bcrypt) oraz tokeny sesji.
"""
import secrets
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


def hash_password(plain: str) -> str:
    return password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> tuple[bool, str | None]:
    if hashed.startswith(("$2a$", "$2b$", "$2y$")):
        # Passlib's former bcrypt configuration truncated inputs at 72 bytes.
        legacy_password = plain.encode("utf-8")[:72]
        valid = password_hash.verify(legacy_password, hashed)
        return valid, hash_password(plain) if valid else None

    return password_hash.verify_and_update(plain, hashed)


def new_session_token() -> str:
    return secrets.token_urlsafe(48)


def new_cookie_id() -> str:
    return secrets.token_urlsafe(24)
