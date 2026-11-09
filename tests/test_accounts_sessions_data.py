"""Regression checks against temporary SQLite databases, without a TCP server."""
import asyncio
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import httpx
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.database import Base, get_db, init_db
from backend.main import app
from backend.models import Language, Progress, Session, StudyAnswer, StudySession, User, UserLanguage, UserWord
from backend.sessions import COOKIE_NAME, SESSION_MAX_AGE
from backend.time_utils import utc_now


class APITestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="langapp-tests-")
        self.addCleanup(temporary.cleanup)
        self.engine = create_async_engine(
            URL.create("sqlite+aiosqlite", database=str(Path(temporary.name) / "test.db")),
            poolclass=NullPool,
        )
        self.addAsyncCleanup(self.engine.dispose)
        await init_db(self.engine)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async def test_db():
            async with self.sessions() as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.addCleanup(app.dependency_overrides.clear)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        )
        self.addAsyncCleanup(self.client.aclose)
        async with self.sessions() as db:
            db.add_all([
                Language(id=1, code="en", name_pl="Angielski", name_native="English", flag_emoji="EN"),
                Language(id=2, code="de", name_pl="Niemiecki", name_native="Deutsch", flag_emoji="DE"),
            ])
            await db.commit()

    async def register(self, login="first", device=None, fingerprint=None, client=None):
        response = await (client or self.client).post("/api/auth/register", json={
            "login": login, "password": "Regression!123", "password_confirm": "Regression!123",
            "cookie_id": device or f"device-{login}-12345",
            "fingerprint": fingerprint or f"fingerprint-{login}-12345",
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["user"]

    async def vocabulary(self):
        response = await self.client.post("/api/user/languages", json={"language_id": 1})
        self.assertEqual(response.status_code, 200, response.text)
        membership = response.json()["user_language_id"]
        words = []
        for word, translation in [("hello", "czesc"), ("house", "dom"), ("cat", "kot"), ("dog", "pies")]:
            response = await self.client.post("/api/user/languages/1/words", json={"word": word, "translation_pl": translation})
            self.assertEqual(response.status_code, 200, response.text)
            words.append(response.json()["word"])
        response = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl", "count": 4})
        self.assertEqual(response.status_code, 200, response.text)
        return membership, words, response.json()

    async def login(self, login="first", device="shared-device-12345", fingerprint="shared-fingerprint-12345"):
        return await self.client.post("/api/auth/login", json={
            "login": login, "password": "Regression!123", "cookie_id": device, "fingerprint": fingerprint,
        })


class AccountDataTests(APITestCase):
    async def test_shared_device_allows_login_to_both_accounts(self):
        await self.register(device="shared-device-12345", fingerprint="shared-fingerprint-12345")
        self.client.cookies.clear()
        second = await self.register("second")
        response = await self.login("second")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.client.get("/api/me")).json()["id"], second["id"])
        # Two matching users must not make the duplicate check throw MultipleResultsFound.
        response = await self.client.post("/api/auth/register", json={
            "login": "third", "password": "Regression!123", "password_confirm": "Regression!123",
            "cookie_id": "shared-device-12345", "fingerprint": "shared-fingerprint-12345",
        })
        self.assertEqual(response.status_code, 403, response.text)

    async def test_changed_fingerprint_does_not_violate_cookie_constraint(self):
        await self.register(device="shared-device-12345")
        await self.register("second", device="shared-device-12345")

    async def test_expired_session_is_rejected_and_removed(self):
        await self.register()
        token = self.client.cookies.get(COOKIE_NAME)
        async with self.sessions() as db:
            session = await db.get(Session, token)
            session.created_at = utc_now() - timedelta(seconds=SESSION_MAX_AGE + 1)
            await db.commit()
        self.assertEqual((await self.client.get("/api/me")).status_code, 401)
        async with self.sessions() as db:
            self.assertIsNone(await db.get(Session, token))

    async def test_login_removes_other_expired_sessions(self):
        await self.register()
        async with self.sessions() as db:
            db.add(Session(token="expired-token", user_id=1, created_at=datetime(2000, 1, 1)))
            await db.commit()
        response = await self.login()
        self.assertEqual(response.status_code, 200, response.text)
        async with self.sessions() as db:
            self.assertIsNone(await db.get(Session, "expired-token"))
        self.assertIn(f"Max-Age={SESSION_MAX_AGE}", response.headers["set-cookie"])

    async def test_login_replaces_previous_browser_session(self):
        await self.register()
        old_token = self.client.cookies.get(COOKIE_NAME)
        self.assertEqual((await self.login()).status_code, 200)
        self.assertEqual((await self.client.get("/api/me")).status_code, 200)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE_NAME, old_token)
        self.assertEqual((await self.client.get("/api/me")).status_code, 401)

    async def test_logout_revokes_replayed_token(self):
        await self.register()
        token = self.client.cookies.get(COOKIE_NAME)
        self.assertEqual((await self.client.post("/api/auth/logout")).status_code, 200)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE_NAME, token)
        self.assertEqual((await self.client.get("/api/me")).status_code, 401)

    async def test_missing_or_unknown_session_is_unauthorized(self):
        self.assertEqual((await self.client.get("/api/me")).status_code, 401)
        self.client.cookies.set(COOKIE_NAME, "unknown")
        self.assertEqual((await self.client.get("/api/me")).status_code, 401)

    async def test_wrong_password_does_not_revoke_valid_session(self):
        await self.register()
        response = await self.client.post("/api/auth/login", json={
            "login": "first", "password": "Incorrect!123", "cookie_id": "device-other", "fingerprint": "fingerprint-other",
        })
        self.assertEqual(response.status_code, 401)
        self.assertEqual((await self.client.get("/api/me")).status_code, 200)

    async def test_concurrent_duplicate_registration_is_a_conflict(self):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver") as other:
            def payload(device):
                return {"login": "duplicate", "password": "Regression!123", "password_confirm": "Regression!123", "cookie_id": device, "fingerprint": device}
            responses = await asyncio.gather(
                self.client.post("/api/auth/register", json=payload("device-one-12345")),
                other.post("/api/auth/register", json=payload("device-two-12345")),
            )
        self.assertEqual(sorted(response.status_code for response in responses), [201, 409])
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(User)), 1)

    async def test_invalid_word_payloads_are_422_and_do_not_write(self):
        await self.register()
        await self.client.post("/api/user/languages", json={"language_id": 1})
        for payload in [
            {"word": 123, "translation_pl": "dom"},
            {"word": "   ", "translation_pl": "dom"},
            {"word": "x" * 129, "translation_pl": "dom"},
            {"word": "house", "translation_pl": None},
            {"word": "house", "translation_pl": "dom", "is_valid": "false"},
        ]:
            with self.subTest(payload=payload):
                response = await self.client.post("/api/user/languages/1/words", json=payload)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.client.get("/api/user/languages/1/words")).json()["words"], [])

    async def test_word_flag_defaults_to_unverified_and_preserves_false(self):
        await self.register()
        await self.client.post("/api/user/languages", json={"language_id": 1})
        for word, extra in [("house", {}), ("cat", {"is_valid": False})]:
            response = await self.client.post("/api/user/languages/1/words", json={"word": word, "translation_pl": "test", **extra})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["word"]["is_valid"])

    async def test_language_and_start_types_are_strict(self):
        await self.register()
        for value in [True, "1", -1, 0, None]:
            response = await self.client.post("/api/user/languages", json={"language_id": value})
            self.assertEqual(response.status_code, 422, response.text)
        for override in [{"mode": []}, {"mode": "unknown"}, {"count": True}, {"count": 51}, {"language_id": True}]:
            response = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "mix", "count": 4, **override})
            self.assertEqual(response.status_code, 422, response.text)

    async def test_inactive_language_cannot_be_added(self):
        await self.register()
        async with self.sessions() as db:
            language = await db.get(Language, 1)
            language.is_active = False
            await db.commit()
        self.assertEqual((await self.client.post("/api/user/languages", json={"language_id": 1})).status_code, 404)

    async def test_invalid_answers_do_not_finish_quiz(self):
        await self.register()
        _, words, quiz = await self.vocabulary()
        word_id = words[0]["id"]
        for answers in [
            [{"word_id": "abc", "given": "dom"}],
            [{"word_id": word_id, "given": 123}],
            [{"word_id": True, "given": "dom"}],
            [{"word_id": word_id, "given": "x" * 129}],
            [{"word_id": word_id}, {"word_id": word_id}],
            [None],
        ]:
            response = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": answers})
            self.assertEqual(response.status_code, 422, response.text)
        response = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": [{"word_id": 999999, "given": "x"}]})
        self.assertEqual(response.status_code, 400, response.text)
        async with self.sessions() as db:
            self.assertFalse((await db.get(StudySession, quiz["session_id"])).finished)
        response = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": [{"word_id": word["id"], "given": word["translation_pl"]} for word in words]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["percent"], 100)

    async def test_language_delete_cleans_all_owned_data_and_isolates_other_users(self):
        first = await self.register()
        first_token = self.client.cookies.get(COOKIE_NAME)
        membership, words, quiz = await self.vocabulary()
        await self.client.post("/api/user/languages", json={"language_id": 2})
        await self.client.post("/api/user/languages/2/words", json={"word": "Haus", "translation_pl": "dom"})
        async with self.sessions() as db:
            db.add(Progress(user_id=first["id"], language="en", xp=10, streak=1))
            await db.commit()
        self.client.cookies.clear()
        second = await self.register("second")
        _, second_words, second_quiz = await self.vocabulary()
        self.assertEqual((await self.client.delete(f"/api/user/languages/{membership}")).status_code, 404)
        self.assertEqual((await self.client.delete(f"/api/words/{words[0]['id']}")).status_code, 404)
        self.assertEqual((await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": []})).status_code, 404)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE_NAME, first_token)
        self.assertEqual((await self.client.delete(f"/api/user/languages/{membership}")).status_code, 200)
        async with self.sessions() as db:
            self.assertIsNone(await db.get(StudySession, quiz["session_id"]))
            self.assertEqual(await db.scalar(select(func.count()).select_from(StudyAnswer).where(StudyAnswer.session_id == quiz["session_id"])), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(Progress).where(Progress.user_id == first["id"])), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(UserWord).where(UserWord.user_id == first["id"], UserWord.language_id == 1)), 0)
            self.assertEqual(await db.scalar(select(func.count()).select_from(UserWord).where(UserWord.user_id == second["id"])), len(second_words))
            self.assertIsNotNone(await db.get(StudySession, second_quiz["session_id"]))
            self.assertEqual(await db.scalar(select(func.count()).select_from(StudyAnswer).where(StudyAnswer.session_id == second_quiz["session_id"])), 4)
        self.assertEqual(len((await self.client.get("/api/user/languages/2/words")).json()["words"]), 1)
        self.assertEqual((await self.client.post("/api/user/languages", json={"language_id": 1})).status_code, 200)
        self.assertEqual((await self.client.get("/api/user/languages/1/words")).json()["words"], [])

    async def test_failed_delete_rolls_back_all_related_changes(self):
        await self.register()
        membership, words, quiz = await self.vocabulary()
        with patch.object(AsyncSession, "commit", side_effect=RuntimeError("simulated commit failure")):
            response = await self.client.delete(f"/api/user/languages/{membership}")
        self.assertEqual(response.status_code, 500)
        async with self.sessions() as db:
            self.assertIsNotNone(await db.get(UserLanguage, membership))
            self.assertIsNotNone(await db.get(StudySession, quiz["session_id"]))
            self.assertEqual(await db.scalar(select(func.count()).select_from(UserWord)), len(words))
            self.assertEqual(await db.scalar(select(func.count()).select_from(StudyAnswer)), 4)

    async def test_fresh_schema_matches_models_and_upgrade_is_idempotent(self):
        await init_db(self.engine)
        async with self.engine.connect() as connection:
            differences = await connection.run_sync(lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata))
        self.assertEqual(differences, [])


class LegacyMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_users_and_sessions_survive_cookie_constraint_removal(self):
        with tempfile.TemporaryDirectory(prefix="langapp-migration-") as directory:
            path = Path(directory) / "legacy.db"
            with sqlite3.connect(path) as connection:
                connection.executescript("""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY, login VARCHAR(64) NOT NULL,
                        password_hash VARCHAR(255) NOT NULL, cookie_id VARCHAR(128) NOT NULL,
                        fingerprint VARCHAR(128) NOT NULL, ip_address VARCHAR(64) NOT NULL,
                        created_at DATETIME NOT NULL, last_login DATETIME NOT NULL,
                        CONSTRAINT uq_cookie_id UNIQUE (cookie_id)
                    );
                    CREATE UNIQUE INDEX ix_users_login ON users(login);
                    INSERT INTO users VALUES (42, 'legacy', 'preserved-hash', 'shared-device-12345',
                        'legacy-fingerprint', '127.0.0.1', '2026-01-01', '2026-01-02');
                    CREATE TABLE sessions (token VARCHAR(128) PRIMARY KEY, user_id INTEGER NOT NULL, created_at DATETIME NOT NULL);
                    INSERT INTO sessions VALUES ('preserved-session',42,'2026-01-02');
                """)
            connection.close()
            engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(path)), poolclass=NullPool)
            try:
                await init_db(engine)
                await init_db(engine)
                async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                    user = await db.get(User, 42)
                    self.assertEqual(user.password_hash, "preserved-hash")
                    self.assertEqual(user.login, "legacy")
                    self.assertEqual(user.created_at, datetime(2026, 1, 1))
                    self.assertEqual((await db.get(Session, "preserved-session")).user_id, 42)
                    db.add(User(login="second", password_hash="another-hash", cookie_id=user.cookie_id, fingerprint="other-fingerprint", ip_address="127.0.0.1"))
                    await db.commit()
                async with engine.connect() as db:
                    constraints = await db.run_sync(lambda sync: inspect(sync).get_unique_constraints("users"))
                    self.assertFalse(any(item["column_names"] == ["cookie_id"] for item in constraints))
            finally:
                await engine.dispose()


if __name__ == "__main__":
    unittest.main()
