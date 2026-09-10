"""
Schematy Pydantic — walidacja żądań i odpowiedzi.
"""
from pydantic import BaseModel, Field, field_validator
import re

PASSWORD_RE = re.compile(
    r"^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{6,}$"
)


class RegisterRequest(BaseModel):
    login: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    password_confirm: str
    fingerprint: str = Field(min_length=8, max_length=128)
    cookie_id: str = Field(min_length=8, max_length=128)

    @field_validator("login")
    @classmethod
    def login_safe(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", v):
            raise ValueError("Login może zawierać tylko litery, cyfry, _ . -")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        if not PASSWORD_RE.match(v):
            raise ValueError(
                "Hasło musi mieć min. 6 znaków, w tym wielką literę, cyfrę i znak specjalny."
            )
        return v


class LoginRequest(BaseModel):
    login: str
    password: str
    fingerprint: str
    cookie_id: str


class UserOut(BaseModel):
    id: int
    login: str
    created_at: str