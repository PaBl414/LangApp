"""
Warstwa bazy danych: silnik async SQLite + sesje SQLAlchemy.
"""
import os
from pathlib import Path
from collections.abc import AsyncIterator

from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession, AsyncEngine
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


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db(db_engine: AsyncEngine | None = None) -> None:
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
    def upgrade(connection):
        config = Config(str(BASE_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BASE_DIR / "migrations"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    async with (db_engine if db_engine is not None else engine).begin() as conn:
        await conn.run_sync(upgrade)
