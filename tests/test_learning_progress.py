"""Deterministic statistics and scheduling checks without a network listener."""
import asyncio
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.database import BASE_DIR, init_db
from backend.learning_stats import current_streak
from backend.models import StudyAnswer, StudySession, WordReview
from backend.reviews import next_review
from backend.time_utils import learning_date
from test_accounts_sessions_data import APITestCase

NOW = datetime(2026, 11, 9, 10)


class CalendarTests(unittest.TestCase):
    def test_calendar_uses_explicit_timezone_including_dst(self):
        with patch("backend.time_utils.LEARNING_TIMEZONE", "Europe/Warsaw"):
            self.assertEqual(learning_date(datetime(2026, 11, 9, 23, 30)), date(2026, 11, 10))
            self.assertEqual(learning_date(datetime(2026, 7, 1, 22, 30)), date(2026, 7, 2))
            self.assertEqual(learning_date(datetime(2026, 1, 1, 22, 30)), date(2026, 1, 1))

    def test_schedule_grows_is_capped_and_resets_after_a_miss(self):
        streak = 0
        for interval in [1, 3, 7, 14, 30, 60, 60]:
            streak, due = next_review(streak, True, NOW)
            self.assertEqual(due, date(2026, 11, 9) + timedelta(days=interval))
        self.assertEqual(next_review(streak, False, NOW), (0, date(2026, 11, 9)))
        self.assertEqual(next_review(0, True, NOW)[1], date(2026, 11, 10))

    def test_streak_counts_distinct_days_and_expires_after_a_gap(self):
        days = {date(2026, 11, 7), date(2026, 11, 8), date(2026, 11, 9)}
        self.assertEqual(current_streak(days, date(2026, 11, 9)), 3)
        self.assertEqual(current_streak(days, date(2026, 11, 10)), 3)
        self.assertEqual(current_streak(days, date(2026, 11, 11)), 0)
        self.assertEqual(current_streak(set(), date(2026, 11, 9)), 0)


class ProgressTests(APITestCase):
    async def test_dashboard_offers_only_owned_unfinished_session_without_answers(self):
        _, words, quiz = await self.setup_quiz()
        data = await self.dashboard()
        self.assertEqual(data["active_session"], {"session_id": quiz["session_id"], "language_id": 1, "current_index": 0, "total": 4})
        await self.finish(words, quiz)
        self.assertIsNone((await self.dashboard())["active_session"])

    async def test_dashboard_continue_never_exposes_another_accounts_draft(self):
        await self.setup_quiz()
        self.client.cookies.clear()
        await self.register("second")
        self.assertIsNone((await self.dashboard())["active_session"])

    async def test_dashboard_requires_authentication(self):
        self.assertEqual((await self.client.get("/api/dashboard")).status_code, 401)
        self.assertEqual((await self.client.get("/api/dashboard/history")).status_code, 401)

    async def setup_quiz(self):
        await self.register()
        return await self.vocabulary()

    async def dashboard(self, when=NOW):
        with patch("backend.routers.learning.utc_now", return_value=when):
            response = await self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def finish(self, words, quiz, when=NOW, miss=None):
        answers = [{"word_id": word["id"], "given": "wrong" if word["id"] == miss else word["translation_pl"]} for word in words]
        with patch("backend.routers.study.utc_now", return_value=when):
            response = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": answers})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_empty_dashboard_has_no_false_accuracy_or_due_cards(self):
        await self.register()
        data = await self.dashboard()
        self.assertEqual(data["summary"]["total_words"], 0)
        self.assertEqual(data["summary"]["practiced_words"], 0)
        self.assertIsNone(data["summary"]["accuracy"])
        self.assertEqual(data["due"], [])
        self.assertEqual(data["difficult"], [])
        self.assertEqual(data["history"]["items"], [])

    async def test_drafts_do_not_award_practice_or_create_reviews(self):
        _, words, quiz = await self.setup_quiz()
        response = await self.client.put(f"/api/study/sessions/{quiz['session_id']}/draft", json={"revision": 0, "current_index": 1, "answers": [{"word_id": words[0]["id"], "given": words[0]["translation_pl"]}]})
        self.assertEqual(response.status_code, 200)
        data = await self.dashboard()
        self.assertEqual(data["summary"]["total_words"], 4)
        self.assertEqual(data["summary"]["practiced_words"], 0)
        self.assertEqual(data["summary"]["quizzes"], 0)
        self.assertEqual(data["history"]["total"], 0)

    async def test_completion_counts_once_and_missed_word_is_due_today(self):
        _, words, quiz = await self.setup_quiz()
        result = await self.finish(words, quiz, miss=words[0]["id"])
        retried = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": []})
        self.assertEqual(retried.json(), result)
        data = await self.dashboard()
        self.assertEqual(data["summary"], {"total_words": 4, "practiced_words": 4, "quizzes": 1, "answers": 4, "correct": 3, "accuracy": 75, "streak": 1, "xp": 30, "due_reviews": 1})
        self.assertEqual(data["due"][0]["direction"], "lang_to_pl")
        self.assertEqual(data["difficult"][0]["word_id"], words[0]["id"])
        self.assertEqual(data["history"]["items"][0]["id"], quiz["session_id"])
        self.assertEqual(data["history"]["items"][0]["percent"], 75)
        async with self.sessions() as db:
            reviews = (await db.execute(select(WordReview))).scalars().all()
            self.assertEqual(len(reviews), 4)
            self.assertTrue(all(review.attempts == 1 for review in reviews))
        progress = await self.client.get("/api/progress")
        self.assertEqual(progress.json()[0]["xp"], 30)

    async def test_due_selection_uses_direction_date_and_supports_one_word(self):
        _, words, quiz = await self.setup_quiz()
        await self.finish(words, quiz)
        self.assertEqual((await self.dashboard())["due"], [])
        tomorrow = NOW + timedelta(days=1)
        self.assertEqual((await self.dashboard(tomorrow))["due"][0]["count"], 4)
        async with self.sessions() as db:
            reviews = (await db.execute(select(WordReview))).scalars().all()
            for review in reviews:
                if review.word_id != words[0]["id"]:
                    review.due_on = date(2026, 12, 1)
            await db.commit()
        with patch("backend.routers.study.utc_now", return_value=tomorrow):
            response = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl", "source": "due", "count": 10})
            empty_reverse = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "pl_to_lang", "source": "due"})
        self.assertEqual(response.status_code, 200, response.text)
        due_quiz = response.json()
        self.assertEqual(due_quiz["source"], "due")
        self.assertEqual(due_quiz["total"], 1)
        self.assertEqual(due_quiz["questions"][0]["word_id"], words[0]["id"])
        self.assertEqual(empty_reverse.status_code, 400)
        await self.finish([words[0]], due_quiz, tomorrow)
        async with self.sessions() as db:
            review = (await db.execute(select(WordReview).where(WordReview.word_id == words[0]["id"]))).scalar_one()
            self.assertEqual(review.consecutive_correct, 2)
            self.assertEqual(review.due_on, date(2026, 11, 13))

    async def test_due_source_is_validated_and_is_part_of_start_idempotency(self):
        await self.setup_quiz()
        request_id = str(uuid4())
        first = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl", "request_id": request_id})
        self.assertEqual(first.status_code, 200)
        changed = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl", "source": "due", "request_id": request_id})
        self.assertEqual(changed.status_code, 409)
        invalid = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "mix", "source": "due"})
        self.assertEqual(invalid.status_code, 422)

    async def test_statistics_and_due_cards_are_isolated_by_account(self):
        _, words, quiz = await self.setup_quiz()
        await self.finish(words, quiz, miss=words[0]["id"])
        self.client.cookies.clear()
        await self.register("second")
        await self.client.post("/api/user/languages", json={"language_id": 1})
        data = await self.dashboard()
        self.assertEqual(data["summary"]["quizzes"], 0)
        self.assertEqual(data["summary"]["practiced_words"], 0)
        self.assertEqual(data["due"], [])
        self.assertEqual(data["difficult"], [])
        self.assertEqual(data["history"]["total"], 0)
        with patch("backend.routers.study.utc_now", return_value=NOW):
            response = await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl", "source": "due"})
        self.assertEqual(response.status_code, 400)

    async def test_failed_transaction_does_not_award_reviews(self):
        _, words, quiz = await self.setup_quiz()
        with patch.object(AsyncSession, "commit", side_effect=RuntimeError("simulated failure")):
            response = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": []})
        self.assertEqual(response.status_code, 500)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(WordReview)), 0)
        self.assertEqual((await self.dashboard())["summary"]["quizzes"], 0)
        await self.finish(words, quiz)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.sum(WordReview.attempts))), 4)

    async def test_concurrent_quizzes_accumulate_instead_of_losing_attempts(self):
        _, words, first = await self.setup_quiz()
        second = (await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl"})).json()
        answers = [{"word_id": word["id"], "given": word["translation_pl"]} for word in words]
        responses = await asyncio.gather(*[self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": answers}) for quiz in [first, second]])
        self.assertEqual([response.status_code for response in responses], [200, 200])
        async with self.sessions() as db:
            reviews = (await db.execute(select(WordReview))).scalars().all()
            self.assertTrue(all(review.attempts == 2 and review.correct_answers == 2 for review in reviews))

    async def test_word_edits_reset_review_but_preserve_history(self):
        _, words, quiz = await self.setup_quiz()
        await self.finish(words, quiz)
        response = await self.client.put(f"/api/words/{words[0]['id']}", json={"word": words[0]["word"], "translation_pl": "changed"})
        self.assertEqual(response.status_code, 200)
        data = await self.dashboard()
        self.assertEqual(data["summary"]["practiced_words"], 3)
        self.assertEqual(data["history"]["total"], 1)
        self.assertEqual(data["history"]["items"][0]["correct"], 4)

    async def test_old_snapshot_cannot_schedule_new_word_content(self):
        _, words, quiz = await self.setup_quiz()
        await self.client.put(f"/api/words/{words[0]['id']}", json={"word": words[0]["word"], "translation_pl": "changed"})
        await self.finish(words, quiz)
        data = await self.dashboard()
        self.assertEqual(data["summary"]["practiced_words"], 3)
        self.assertEqual(data["summary"]["correct"], 4)

    async def test_word_and_language_deletion_clear_review_state(self):
        membership, words, quiz = await self.setup_quiz()
        await self.finish(words, quiz, miss=words[0]["id"])
        await self.client.delete(f"/api/words/{words[0]['id']}")
        data = await self.dashboard()
        self.assertEqual(data["summary"]["practiced_words"], 3)
        self.assertEqual(data["difficult"], [])
        self.assertEqual(data["history"]["total"], 1)
        self.assertEqual((await self.client.delete(f"/api/user/languages/{membership}")).status_code, 200)
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(WordReview)), 0)
        self.assertEqual((await self.dashboard())["history"]["total"], 0)

    async def test_history_pagination_is_bounded_and_completed_only(self):
        _, words, _ = await self.setup_quiz()
        async with self.sessions() as db:
            for index in range(21):
                quiz = StudySession(user_id=1, language_id=1, mode="lang_to_pl", total=1, correct=1, finished=True, finished_at=NOW + timedelta(minutes=index))
                db.add(quiz)
                await db.flush()
                db.add(StudyAnswer(session_id=quiz.id, word_id=words[0]["id"], prompt="hello", expected="czesc", given="czesc", is_correct=True, direction="lang_to_pl"))
            await db.commit()
        first = (await self.dashboard())["history"]
        second = (await self.client.get("/api/dashboard/history?limit=10&offset=10")).json()
        third = (await self.client.get("/api/dashboard/history?limit=10&offset=20")).json()
        self.assertEqual((len(first["items"]), len(second["items"]), len(third["items"])), (10, 10, 1))
        self.assertEqual(first["total"], 21)
        self.assertIsNone(third["next_offset"])
        self.assertEqual(len({item["id"] for page in [first, second, third] for item in page["items"]}), 21)
        for query in ["limit=51", "offset=-1"]:
            self.assertEqual((await self.client.get("/api/dashboard/history?" + query)).status_code, 422)


class ReviewMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_migration_rolls_back_ddl_and_can_be_retried(self):
        with tempfile.TemporaryDirectory(prefix="langapp-migration-failure-") as directory:
            engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(Path(directory) / "old.db")), poolclass=NullPool)
            try:
                def old_schema(connection):
                    config = Config(str(BASE_DIR / "alembic.ini"))
                    config.attributes["connection"] = connection
                    command.upgrade(config, "0002_reliable_quizzes")
                async with engine.begin() as connection:
                    await connection.run_sync(old_schema)
                with patch("alembic.op.create_index", side_effect=RuntimeError("simulated DDL failure")):
                    with self.assertRaisesRegex(RuntimeError, "simulated DDL failure"):
                        await init_db(engine)
                async with engine.connect() as connection:
                    revision = (await connection.exec_driver_sql("SELECT version_num FROM alembic_version")).scalar_one()
                    self.assertEqual(revision, "0002_reliable_quizzes")
                    fields = (await connection.exec_driver_sql("PRAGMA table_info(study_sessions)")).all()
                    self.assertNotIn("source", [row[1] for row in fields])
                    tables = (await connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")).scalars().all()
                    self.assertNotIn("word_reviews", tables)
                await init_db(engine)
            finally:
                await engine.dispose()

    async def test_historical_results_are_backfilled_once_and_edited_snapshots_are_skipped(self):
        with tempfile.TemporaryDirectory(prefix="langapp-reviews-") as directory:
            engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(Path(directory) / "old.db")), poolclass=NullPool)
            try:
                def old_schema(connection):
                    config = Config(str(BASE_DIR / "alembic.ini"))
                    config.attributes["connection"] = connection
                    command.upgrade(config, "0002_reliable_quizzes")
                async with engine.begin() as connection:
                    await connection.run_sync(old_schema)
                    await connection.exec_driver_sql("INSERT INTO user_words (id,user_id,language_id,word,translation_pl,is_valid,created_at) VALUES (1,1,1,'hello','czesc',1,'2026-01-01'),(2,1,1,'edited','new meaning',1,'2026-01-01')")
                    for number, correct in [(1, 0), (2, 1)]:
                        await connection.exec_driver_sql("INSERT INTO study_sessions (id,user_id,language_id,mode,total,correct,finished,created_at,finished_at) VALUES (?,1,1,'lang_to_pl',2,?,1,'2026-11-08','2026-11-09 10:00:00')", (number, correct))
                        await connection.exec_driver_sql("INSERT INTO study_answers (session_id,word_id,prompt,expected,given,is_correct,direction,created_at) VALUES (?,1,'hello','czesc','answer',?,'lang_to_pl','2026-11-09')", (number, correct))
                        await connection.exec_driver_sql("INSERT INTO study_answers (session_id,word_id,prompt,expected,given,is_correct,direction,created_at) VALUES (?,2,'edited','old meaning','answer',0,'lang_to_pl','2026-11-09')", (number,))
                await init_db(engine)
                await init_db(engine)
                async with async_sessionmaker(engine)() as db:
                    reviews = (await db.execute(select(WordReview))).scalars().all()
                    self.assertEqual(len(reviews), 1)
                    self.assertEqual((reviews[0].attempts, reviews[0].correct_answers, reviews[0].consecutive_correct), (2, 1, 1))
                    self.assertEqual(reviews[0].due_on, date(2026, 11, 10))
                    self.assertEqual(await db.scalar(select(func.count()).select_from(StudyAnswer)), 4)
            finally:
                await engine.dispose()


if __name__ == "__main__":
    unittest.main()
