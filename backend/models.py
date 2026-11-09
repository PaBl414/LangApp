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
class Language(Base):
    """Lista 50 najpopularniejszych języków do nauki."""
    __tablename__ = "languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(8), unique=True, index=True, nullable=False)  # ISO 639-1, np. "en"
    name_pl: Mapped[str] = mapped_column(String(64), nullable=False)   # np. "Angielski"
    name_native: Mapped[str] = mapped_column(String(64), nullable=False)  # np. "English"
    flag_emoji: Mapped[str] = mapped_column(String(16), nullable=False)   # np. "🇬🇧"
    is_active: Mapped[bool] = mapped_column(default=True)


class UserLanguage(Base):
    """Języki dodane przez konkretnego użytkownika."""
    __tablename__ = "user_languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    language_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "language_id", name="uq_user_language"),
    )


class UserWord(Base):
    """Słowa użytkownika w danym języku. (Etap 2 — teraz tylko szkielet.)"""
    __tablename__ = "user_words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    language_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    word: Mapped[str] = mapped_column(String(128), nullable=False)          # słowo w języku obcym
    translation_pl: Mapped[str] = mapped_column(String(128), nullable=False)  # tłumaczenie polskie
    is_valid: Mapped[bool] = mapped_column(default=True)                    # czy przeszło walidację API
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
class StudySession(Base):
    """Sesja nauki — jedno podejście użytkownika do quizu."""
    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    language_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "lang_to_pl" | "pl_to_lang" | "mix"
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[int] = mapped_column(Integer, default=0)
    finished: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)


class StudyAnswer(Base):
    """Pojedyncza odpowiedź w sesji nauki."""
    __tablename__ = "study_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    word_id: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(String(128), nullable=False)       # co pokazano
    expected: Mapped[str] = mapped_column(String(128), nullable=False)     # poprawna odpowiedź
    given: Mapped[str] = mapped_column(String(128), nullable=False)        # co wpisał/kliknął użytkownik
    is_correct: Mapped[bool] = mapped_column(default=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)     # "lang_to_pl" | "pl_to_lang"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
