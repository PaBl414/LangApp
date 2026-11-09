"""
Warstwa bazy danych: silnik async SQLite + sesje SQLAlchemy.
"""
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_URL = URL.create(
    "sqlite+aiosqlite", database=str(BASE_DIR / "data" / "langapp.db")
)
DATABASE_URL = os.getenv("LANGAPP_DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    # import modeli, aby zarejestrować tabele
    from . import models  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
