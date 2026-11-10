"""Examples, tag filtering, trash retention and ownership using isolated SQLite."""
import asyncio
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.database import BASE_DIR, init_db
from backend.models import UserWord, WordReview
from backend.time_utils import utc_now
from test_accounts_sessions_data import APITestCase


class VocabularyExperienceTests(APITestCase):
    async def setup_words(self):
        await self.register()
        return await self.vocabulary()

    async def finish_quiz(self, words, quiz):
        return await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"],
            "answers": [{"word_id": word["id"], "given": word["translation_pl"]} for word in words]})

    async def test_examples_snapshot_tag_filter_and_idempotent_configuration(self):
        _, words, _ = await self.setup_words()
        metadata = {"word": words[0]["word"], "translation_pl": words[0]["translation_pl"],
            "tags": ["Ważne", "WAŻNE", "Do pracy"], "example_sentence": "Hello, my friend.",
            "example_translation": "Cześć, mój przyjacielu."}
        updated = await self.client.put(f"/api/words/{words[0]['id']}", json=metadata)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["word"]["tags"], ["Ważne", "Do pracy"])
        settings = {"language_id": 1, "mode": "lang_to_pl", "count": 10, "tag": "ważne", "request_id": str(uuid4())}
        started = await self.client.post("/api/study/start", json=settings)
        self.assertEqual(started.status_code, 200, started.text)
        quiz = started.json()
        self.assertEqual(quiz["total"], 1)
        self.assertEqual(quiz["questions"][0]["context"], metadata["example_sentence"])
        self.assertNotIn(metadata["example_translation"], started.text)
        self.assertNotIn("expected", quiz["questions"][0])
        settings["tag"] = "Do pracy"
        self.assertEqual((await self.client.post("/api/study/start", json=settings)).status_code, 409)
        await self.client.put(f"/api/words/{words[0]['id']}", json={**metadata, "example_sentence": "Different context.", "example_translation": "Inny kontekst."})
        result = await self.finish_quiz([words[0]], quiz)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["results"][0]["example_sentence"], metadata["example_sentence"])
        reverse = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "pl_to_lang", "tag": "Ważne"})
        self.assertEqual(reverse.status_code, 200, reverse.text)
        self.assertEqual(reverse.json()["questions"][0]["context"], "Inny kontekst.")
        self.assertNotIn("Different context.", reverse.text)

    async def test_metadata_only_edit_preserves_reviews_and_old_clients_preserve_metadata(self):
        _, words, quiz = await self.setup_words()
        await self.finish_quiz(words, quiz)
        async with self.sessions() as db:
            before = (await db.execute(select(WordReview).where(WordReview.word_id == words[0]["id"])) ).scalar_one()
            state = (before.attempts, before.due_on)
        payload = {"word": words[0]["word"], "translation_pl": words[0]["translation_pl"], "tags": ["Trudne"],
            "example_sentence": "Hello there.", "example_translation": "Cześć."}
        self.assertEqual((await self.client.put(f"/api/words/{words[0]['id']}", json=payload)).status_code, 200)
        response = await self.client.put(f"/api/words/{words[0]['id']}", json={"word": words[0]["word"], "translation_pl": words[0]["translation_pl"]})
        self.assertEqual(response.json()["word"]["tags"], ["Trudne"])
        self.assertEqual(response.json()["word"]["example_sentence"], "Hello there.")
        async with self.sessions() as db:
            after = (await db.execute(select(WordReview).where(WordReview.word_id == words[0]["id"]))).scalar_one()
            self.assertEqual((after.attempts, after.due_on), state)

    async def test_metadata_validation_rejects_partial_examples_and_bad_tags_without_write(self):
        await self.register()
        await self.client.post("/api/user/languages", json={"language_id": 1})
        base = {"word": "hello", "translation_pl": "cześć"}
        invalid = [{"example_sentence": "Only one side"}, {"example_translation": "Tylko tłumaczenie"},
            {"example_sentence": "x" * 501, "example_translation": "za długo"}, {"tags": ["x" * 33]},
            {"tags": ["bad,tag"]}, {"tags": ["line\nbreak"]}, {"tags": [str(i) for i in range(11)]}, {"tags": [False]}]
        for values in invalid:
            response = await self.client.post("/api/user/languages/1/words", json={**base, **values})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual((await self.client.get("/api/user/languages/1/words")).json()["words"], [])

    async def test_trash_restore_preserves_metadata_review_state_and_finished_history(self):
        _, words, quiz = await self.setup_words()
        await self.finish_quiz(words, quiz)
        word = words[0]
        await self.client.put(f"/api/words/{word['id']}", json={"word": word["word"], "translation_pl": word["translation_pl"],
            "tags": ["Ważne"], "example_sentence": "Hello!", "example_translation": "Cześć!"})
        async with self.sessions() as db:
            review = (await db.execute(select(WordReview).where(WordReview.word_id == word["id"]))).scalar_one()
            before = (review.attempts, review.correct_answers, review.due_on)
        deleted = await self.client.delete(f"/api/words/{word['id']}")
        self.assertEqual(deleted.status_code, 200)
        retry = await self.client.delete(f"/api/words/{word['id']}")
        self.assertEqual(retry.json()["expires_at"], deleted.json()["expires_at"])
        trash = (await self.client.get("/api/user/languages/1/trash")).json()["words"]
        self.assertEqual(trash[0]["tags"], ["Ważne"])
        self.assertEqual(len((await self.client.get("/api/user/languages/1/words")).json()["words"]), 3)
        self.assertEqual((await self.client.get("/api/dashboard")).json()["summary"]["practiced_words"], 3)
        self.assertEqual((await self.client.put(f"/api/words/{word['id']}", json={"word": word["word"], "translation_pl": word["translation_pl"]})).status_code, 404)
        for _ in range(2):
            response = await self.client.post(f"/api/words/{word['id']}/restore")
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len((await self.client.get("/api/user/languages/1/words")).json()["words"]), 4)
        async with self.sessions() as db:
            review = (await db.execute(select(WordReview).where(WordReview.word_id == word["id"]))).scalar_one()
            self.assertEqual((review.attempts, review.correct_answers, review.due_on), before)
        self.assertEqual((await self.client.get("/api/dashboard")).json()["history"]["total"], 1)

    async def test_trash_is_excluded_from_tag_quizzes_and_review_awards(self):
        _, words, quiz = await self.setup_words()
        await self.client.put(f"/api/words/{words[0]['id']}", json={"word": words[0]["word"], "translation_pl": words[0]["translation_pl"], "tags": ["Trudne"]})
        await self.client.delete(f"/api/words/{words[0]['id']}")
        self.assertEqual((await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl", "tag": "Trudne"})).status_code, 400)
        result = await self.finish_quiz(words, quiz)
        self.assertEqual(result.json()["correct"], 4)
        async with self.sessions() as db:
            self.assertIsNone(await db.scalar(select(WordReview).where(WordReview.word_id == words[0]["id"])))

    async def test_conflicting_restore_is_atomic_and_concurrent_add_never_overwrites(self):
        _, words, _ = await self.setup_words()
        word = words[0]
        await self.client.delete(f"/api/words/{word['id']}")
        responses = await asyncio.gather(self.client.post(f"/api/words/{word['id']}/restore"),
            self.client.post("/api/user/languages/1/words", json={"word": word["word"], "translation_pl": "inne"}))
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409], [response.text for response in responses])
        active = (await self.client.get("/api/user/languages/1/words")).json()["words"]
        self.assertEqual(sum(item["word"] == word["word"] for item in active), 1)

    async def test_expiry_and_permanent_deletion_keep_historical_snapshots(self):
        _, words, quiz = await self.setup_words()
        await self.finish_quiz(words, quiz)
        self.assertEqual((await self.client.delete(f"/api/words/{words[0]['id']}/permanent")).status_code, 400)
        await self.client.delete(f"/api/words/{words[0]['id']}")
        async with self.sessions() as db:
            word = await db.get(UserWord, words[0]["id"])
            word.deleted_at = utc_now() - timedelta(days=8)
            await db.commit()
        self.assertEqual((await self.client.post(f"/api/words/{words[0]['id']}/restore")).status_code, 404)
        self.assertEqual((await self.client.get("/api/user/languages/1/trash")).json()["words"], [])
        async with self.sessions() as db:
            self.assertIsNone(await db.get(UserWord, words[0]["id"]))
        await self.client.delete(f"/api/words/{words[1]['id']}")
        self.assertEqual((await self.client.delete(f"/api/words/{words[1]['id']}/permanent")).status_code, 200)
        self.assertEqual((await self.client.get(f"/api/study/sessions/{quiz['session_id']}")).json()["result"]["correct"], 4)

    async def test_other_accounts_cannot_inspect_restore_or_purge_trash(self):
        _, words, _ = await self.setup_words()
        await self.client.delete(f"/api/words/{words[0]['id']}")
        self.client.cookies.clear()
        await self.register("second")
        for method, path in [("GET", "/api/user/languages/1/trash"), ("POST", f"/api/words/{words[0]['id']}/restore"), ("DELETE", f"/api/words/{words[0]['id']}/permanent")]:
            self.assertEqual((await self.client.request(method, path)).status_code, 404)

    async def test_reused_row_id_cannot_receive_credit_from_an_old_quiz(self):
        _, words, quiz = await self.setup_words()
        removed = words[-1]
        await self.client.delete(f"/api/words/{removed['id']}")
        await self.client.delete(f"/api/words/{removed['id']}/permanent")
        response = await self.client.post("/api/user/languages/1/words", json={"word": removed["word"], "translation_pl": removed["translation_pl"]})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["word"]["id"], removed["id"])
        await self.finish_quiz(words, quiz)
        async with self.sessions() as db:
            self.assertIsNone(await db.scalar(select(WordReview).where(WordReview.word_id == removed["id"])))


class VocabularyMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_upgrade_from_v3_preserves_rows_and_failed_ddl_rolls_back(self):
        with tempfile.TemporaryDirectory(prefix="langapp-context-migration-") as directory:
            engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(Path(directory) / "old.db")))
            try:
                def upgrade_v3(connection):
                    config = Config(str(BASE_DIR / "alembic.ini")); config.attributes["connection"] = connection
                    command.upgrade(config, "0003_learning_progress")
                async with engine.begin() as connection:
                    await connection.run_sync(upgrade_v3)
                    await connection.exec_driver_sql("INSERT INTO user_words (id,user_id,language_id,word,translation_pl,is_valid,created_at) VALUES (1,1,1,'hello','czesc',0,'2026-01-01')")
                def fail_index(*args, **kwargs):
                    raise RuntimeError("simulated DDL failure")
                with patch("alembic.operations.Operations.create_index", new=fail_index):
                    with self.assertRaises(RuntimeError): await init_db(engine)
                async with engine.connect() as connection:
                    columns = {row[1] for row in (await connection.exec_driver_sql("PRAGMA table_info(user_words)")).all()}
                    self.assertNotIn("example_sentence", columns)
                await init_db(engine); await init_db(engine)
                async with async_sessionmaker(engine)() as db:
                    word = await db.get(UserWord, 1)
                    self.assertEqual((word.word, word.translation_pl, word.tags, word.example_sentence, word.deleted_at), ("hello", "czesc", [], "", None))
            finally:
                await engine.dispose()
