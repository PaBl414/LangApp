"""
Modele ORM. Tabela users przechowuje login, hash hasła,
informacje o cookies, fingerprint oraz lokalny adres IP.
"""
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Bezpieczeństwo / antifraud
    cookie_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("cookie_id", name="uq_cookie_id"),
    )


class Session(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Progress(Base):
    """Prosty postęp nauki — miejsce na rozbudowę."""
    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="en")
    xp: Mapped[int] = mapped_column(Integer, default=0)
    streak: Mapped[int] = mapped_column(Integer, default=0)