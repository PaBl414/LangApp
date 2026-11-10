"""
Modele ORM. Tabela users przechowuje login, hash hasła,
informacje o cookies, fingerprint oraz lokalny adres IP.
"""
from datetime import date, datetime
from sqlalchemy import String, Integer, Date, DateTime, JSON, Index, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .time_utils import utc_now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    login: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # Bezpieczeństwo / antifraud
    cookie_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    last_login: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

class Session(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Progress(Base):
    """Legacy prototype counters, preserved; current statistics are derived from quizzes."""
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("user_id", "language_id", name="uq_user_language"),
    )


class UserWord(Base):
    """Owned vocabulary and explicit accepted answers in both translation directions."""
    __tablename__ = "user_words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    language_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    word: Mapped[str] = mapped_column(String(128), nullable=False)          # słowo w języku obcym
    translation_pl: Mapped[str] = mapped_column(String(128), nullable=False)  # tłumaczenie polskie
    translation_alternatives: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    word_alternatives: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    example_sentence: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    example_translation: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_valid: Mapped[bool] = mapped_column(default=True)                    # czy przeszło walidację API
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (Index("ix_user_words_trash", "user_id", "language_id", "deleted_at"),)
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    current_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    start_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    requested_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(8), default="all", server_default="all", nullable=False)
    tag: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("uq_study_start_request", "user_id", "start_request_id", unique=True),
    )


class StudyAnswer(Base):
    """Pojedyncza odpowiedź w sesji nauki."""
    __tablename__ = "study_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    word_id: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(String(128), nullable=False)       # co pokazano
    expected: Mapped[str] = mapped_column(String(128), nullable=False)     # poprawna odpowiedź
    accepted_answers: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]", nullable=False)
    example_sentence: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    example_translation: Mapped[str] = mapped_column(String(500), default="", server_default="", nullable=False)
    given: Mapped[str] = mapped_column(String(128), nullable=False)        # co wpisał/kliknął użytkownik
    is_correct: Mapped[bool] = mapped_column(default=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)     # "lang_to_pl" | "pl_to_lang"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class WordReview(Base):
    """Current learning state for an owned word and one translation direction."""
    __tablename__ = "word_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    word_id: Mapped[int] = mapped_column(Integer, nullable=False)
    language_id: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_correct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)
    last_correct: Mapped[bool] = mapped_column(nullable=False)
    last_reviewed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "word_id", "direction", name="uq_word_review_direction"),
        CheckConstraint("attempts >= 0 AND correct_answers >= 0 AND correct_answers <= attempts", name="ck_word_review_counts"),
        CheckConstraint("consecutive_correct >= 0", name="ck_word_review_streak"),
        Index("ix_word_reviews_due", "user_id", "due_on", "language_id", "direction"),
    )
