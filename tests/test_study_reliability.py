"""Network-free regressions for quiz recovery, concurrency and answer grading."""
import asyncio
import unittest
import tempfile
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool
from alembic import command
from alembic.config import Config

from backend.grading import accepted_variants, is_correct, normalize_answer
from backend.models import StudyAnswer, StudySession, UserWord
from backend.database import BASE_DIR, init_db
from test_accounts_sessions_data import APITestCase


class GradingTests(unittest.TestCase):
    def test_equivalent_unicode_case_and_whitespace(self):
        self.assertEqual(normalize_answer("  CAFE\u0301\u00a0  au\tlait\n"), normalize_answer("café au lait"))
        self.assertTrue(is_correct(" STRASSE ", "Straße", []))

    def test_accents_punctuation_and_spelling_remain_significant(self):
        for given, expected in [("si", "sí"), ("lodz", "łódź"), ("wellbeing", "well-being"), ("horse", "house"), ("", ""), ("  ", "dom")]:
            with self.subTest(given=given, expected=expected):
                self.assertFalse(is_correct(given, expected, []))

    def test_variants_are_explicit_and_deduplicated(self):
        self.assertEqual(accepted_variants("Cześć", [" cześć ", "Witaj", "WITAJ"]), ["Cześć", "Witaj"])
        self.assertTrue(is_correct(" witaj ", "cześć", ["Witaj"]))
        self.assertFalse(is_correct("dom", "dom, budynek", []))


class ReliableQuizTests(APITestCase):
    async def quiz(self):
        await self.register()
        _, words, quiz = await self.vocabulary()
        return words, quiz

    @staticmethod
    def correct_answers(words):
        return [{"word_id": word["id"], "given": word["translation_pl"]} for word in words]

    async def test_start_retry_reuses_quiz_and_rejects_changed_settings(self):
        await self.quiz()
        request_id = str(uuid4())
        body = {"language_id": 1, "mode": "mix", "count": 10, "request_id": request_id}
        first = await self.client.post("/api/study/start", json=body)
        repeated = await self.client.post("/api/study/start", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), repeated.json())
        async with self.sessions() as db:
            count = await db.scalar(select(func.count()).select_from(StudySession).where(StudySession.start_request_id == request_id))
            self.assertEqual(count, 1)
        conflict = await self.client.post("/api/study/start", json={**body, "count": 3})
        self.assertEqual(conflict.status_code, 409)

    async def test_concurrent_start_creates_one_snapshot(self):
        await self.quiz()
        body = {"language_id": 1, "mode": "mix", "request_id": str(uuid4())}
        responses = await asyncio.gather(*[self.client.post("/api/study/start", json=body) for _ in range(2)])
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json(), responses[1].json())
        async with self.sessions() as db:
            self.assertEqual(await db.scalar(select(func.count()).select_from(StudyAnswer).where(StudyAnswer.session_id == responses[0].json()["session_id"])), 4)

    async def test_draft_survives_reload_and_does_not_reveal_answers(self):
        words, quiz = await self.quiz()
        body = {"revision": 0, "current_index": 2, "answers": self.correct_answers(words)}
        response = await self.client.put(f"/api/study/sessions/{quiz['session_id']}/draft", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        loaded = (await self.client.get(f"/api/study/sessions/{quiz['session_id']}")).json()
        self.assertEqual(loaded["current_index"], 2)
        self.assertEqual(loaded["revision"], 1)
        self.assertEqual({a["word_id"]: a["given"] for a in loaded["answers"]}, {a["word_id"]: a["given"] for a in body["answers"]})
        self.assertNotIn("result", loaded)
        for question in loaded["questions"]:
            self.assertNotIn("expected", question)
            self.assertNotIn("accepted_answers", question)
        active = (await self.client.get("/api/study/active", params={"language_id": 1})).json()["sessions"]
        self.assertEqual(active[0]["session_id"], quiz["session_id"])
        self.assertEqual(active[0]["current_index"], 2)

    async def test_lost_draft_acknowledgement_can_be_retried(self):
        words, quiz = await self.quiz()
        body = {"revision": 0, "current_index": 1, "answers": self.correct_answers(words)}
        first = await self.client.put(f"/api/study/sessions/{quiz['session_id']}/draft", json=body)
        retried = await self.client.put(f"/api/study/sessions/{quiz['session_id']}/draft", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(first.json(), retried.json())

    async def test_stale_tab_cannot_overwrite_saved_draft_or_submit(self):
        words, quiz = await self.quiz()
        path = f"/api/study/sessions/{quiz['session_id']}/draft"
        body = {"revision": 0, "current_index": 1, "answers": self.correct_answers(words)}
        self.assertEqual((await self.client.put(path, json=body)).status_code, 200)
        stale_answers = [{**answer, "given": "wrong"} for answer in body["answers"]]
        self.assertEqual((await self.client.put(path, json={**body, "answers": stale_answers})).status_code, 409)
        self.assertEqual((await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "revision": 0, "answers": stale_answers})).status_code, 409)
        loaded = (await self.client.get(f"/api/study/sessions/{quiz['session_id']}")).json()
        self.assertFalse(loaded["finished"])
        self.assertEqual(loaded["revision"], 1)

    async def test_concurrent_drafts_have_one_winner(self):
        words, quiz = await self.quiz()
        path = f"/api/study/sessions/{quiz['session_id']}/draft"
        responses = await asyncio.gather(*[
            self.client.put(path, json={"revision": 0, "current_index": 1, "answers": [{"word_id": words[0]["id"], "given": text}]})
            for text in ["first tab", "second tab"]
        ])
        self.assertEqual(sorted(response.status_code for response in responses), [200, 409])

    async def test_final_retry_returns_immutable_result_and_get_recovers_it(self):
        words, quiz = await self.quiz()
        body = {"session_id": quiz["session_id"], "revision": 0, "answers": self.correct_answers(words)}
        first = await self.client.post("/api/study/submit", json=body)
        self.assertEqual(first.status_code, 200, first.text)
        retry = await self.client.post("/api/study/submit", json={**body, "answers": []})
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(retry.json(), first.json())
        self.assertEqual(first.json()["percent"], 100)
        loaded = (await self.client.get(f"/api/study/sessions/{quiz['session_id']}")).json()
        self.assertTrue(loaded["finished"])
        self.assertEqual(loaded["result"], first.json())
        self.assertEqual((await self.client.get("/api/study/active", params={"language_id": 1})).json()["sessions"], [])
        self.assertEqual((await self.client.put(f"/api/study/sessions/{quiz['session_id']}/draft", json={"revision": 1, "current_index": 0, "answers": []})).status_code, 409)

    async def test_concurrent_submissions_cannot_change_first_result(self):
        words, quiz = await self.quiz()
        responses = await asyncio.gather(*[
            self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "revision": 0, "answers": answers})
            for answers in [self.correct_answers(words), []]
        ])
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertEqual(responses[0].json(), responses[1].json())
        async with self.sessions() as db:
            self.assertEqual((await db.get(StudySession, quiz["session_id"])).revision, 1)

    async def test_snapshot_alternatives_and_edits_do_not_change_running_quiz(self):
        words, old_quiz = await self.quiz()
        word = words[0]
        response = await self.client.put(f"/api/words/{word['id']}", json={
            "word": word["word"], "translation_pl": word["translation_pl"],
            "translation_alternatives": ["witaj", " WITAJ ", word["translation_pl"]], "word_alternatives": ["hi"],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["word"]["translation_alternatives"], ["witaj"])
        current = (await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl"})).json()
        await self.client.put(f"/api/words/{word['id']}", json={"word": word["word"], "translation_pl": "new primary", "translation_alternatives": ["hej"]})
        answers = self.correct_answers(words)
        answers[0]["given"] = " WITAJ "
        result = await self.client.post("/api/study/submit", json={"session_id": current["session_id"], "answers": answers})
        self.assertEqual(result.json()["percent"], 100)
        old = await self.client.post("/api/study/submit", json={"session_id": old_quiz["session_id"], "answers": answers})
        self.assertEqual(old.json()["correct"], 3)

    async def test_reverse_direction_uses_foreign_alternatives(self):
        words, _ = await self.quiz()
        word = words[0]
        await self.client.put(f"/api/words/{word['id']}", json={"word": word["word"], "translation_pl": word["translation_pl"], "word_alternatives": ["hi"]})
        quiz = (await self.client.post("/api/study/start", json={"language_id": 1, "mode": "pl_to_lang"})).json()
        answers = [{"word_id": w["id"], "given": "hi" if w["id"] == word["id"] else w["word"]} for w in words]
        response = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": answers})
        self.assertEqual(response.json()["percent"], 100)

    async def test_unicode_equivalence_is_applied_by_quiz_endpoint(self):
        words, _ = await self.quiz()
        word = words[0]
        await self.client.put(f"/api/words/{word['id']}", json={"word": word["word"], "translation_pl": "café au lait"})
        quiz = (await self.client.post("/api/study/start", json={"language_id": 1, "mode": "lang_to_pl"})).json()
        answers = self.correct_answers(words)
        answers[0]["given"] = " CAFE\u0301\u00a0  au\tlait "
        response = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": answers})
        self.assertEqual(response.json()["percent"], 100)

    async def test_drafts_and_edits_are_owned_and_validated(self):
        words, quiz = await self.quiz()
        path = f"/api/study/sessions/{quiz['session_id']}/draft"
        for body, status in [
            ({"revision": 0, "current_index": 4, "answers": []}, 400),
            ({"revision": 0, "current_index": 0, "answers": [{"word_id": 99999}]}, 400),
            ({"revision": True, "current_index": 0, "answers": []}, 422),
        ]:
            self.assertEqual((await self.client.put(path, json=body)).status_code, status)
        for aliases in [[""], [123], ["x"] * 11, "not-a-list"]:
            response = await self.client.put(f"/api/words/{words[0]['id']}", json={"word": "hello", "translation_pl": "czesc", "translation_alternatives": aliases})
            self.assertEqual(response.status_code, 422, response.text)
        self.client.cookies.clear()
        await self.register("second")
        self.assertEqual((await self.client.get(f"/api/study/sessions/{quiz['session_id']}")).status_code, 404)
        self.assertEqual((await self.client.put(path, json={"revision": 0, "current_index": 0, "answers": []})).status_code, 404)
        self.assertEqual((await self.client.put(f"/api/words/{words[0]['id']}", json={"word": "hello", "translation_pl": "changed"})).status_code, 404)

    async def test_failed_draft_and_submission_are_atomic(self):
        words, quiz = await self.quiz()
        path = f"/api/study/sessions/{quiz['session_id']}"
        with patch.object(AsyncSession, "commit", side_effect=RuntimeError("simulated commit failure")):
            draft = await self.client.put(path + "/draft", json={"revision": 0, "current_index": 1, "answers": self.correct_answers(words)})
        self.assertEqual(draft.status_code, 500)
        restored = (await self.client.get(path)).json()
        self.assertEqual(restored["revision"], 0)
        self.assertEqual(restored["current_index"], 0)
        self.assertTrue(all(answer["given"] == "" for answer in restored["answers"]))
        with patch.object(AsyncSession, "commit", side_effect=RuntimeError("simulated commit failure")):
            final = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": self.correct_answers(words)})
        self.assertEqual(final.status_code, 500)
        restored = (await self.client.get(path)).json()
        self.assertFalse(restored["finished"])
        self.assertEqual(restored["revision"], 0)
        retry = await self.client.post("/api/study/submit", json={"session_id": quiz["session_id"], "answers": self.correct_answers(words)})
        self.assertEqual(retry.json()["percent"], 100)


class QuizMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_words_and_answer_snapshots_survive_upgrade(self):
        with tempfile.TemporaryDirectory(prefix="langapp-quiz-upgrade-") as directory:
            engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(Path(directory) / "old.db")), poolclass=NullPool)
            try:
                def old_schema(connection):
                    config = Config(str(BASE_DIR / "alembic.ini"))
                    config.attributes["connection"] = connection
                    command.upgrade(config, "0001_accounts_data")
                async with engine.begin() as connection:
                    await connection.run_sync(old_schema)
                    await connection.exec_driver_sql("INSERT INTO user_words (id,user_id,language_id,word,translation_pl,is_valid,created_at) VALUES (1,1,1,'hello','czesc / witaj',1,'2026-01-01')")
                    await connection.exec_driver_sql("INSERT INTO study_sessions (id,user_id,language_id,mode,total,correct,finished,created_at) VALUES (1,1,1,'lang_to_pl',1,0,0,'2026-01-01')")
                    await connection.exec_driver_sql("INSERT INTO study_answers (id,session_id,word_id,prompt,expected,given,is_correct,direction,created_at) VALUES (1,1,1,'hello','czesc / witaj','',0,'lang_to_pl','2026-01-01')")
                await init_db(engine)
                await init_db(engine)
                async with async_sessionmaker(engine)() as db:
                    word = await db.get(UserWord, 1)
                    answer = await db.get(StudyAnswer, 1)
                    quiz = await db.get(StudySession, 1)
                    self.assertEqual(word.translation_pl, "czesc / witaj")
                    self.assertEqual(word.translation_alternatives, [])
                    self.assertEqual(word.word_alternatives, [])
                    self.assertEqual(answer.expected, "czesc / witaj")
                    self.assertEqual(answer.accepted_answers, [])
                    self.assertFalse(is_correct("czesc", answer.expected, answer.accepted_answers))
                    self.assertEqual(quiz.revision, 0)
                    self.assertEqual(quiz.current_index, 0)
                    self.assertIsNone(quiz.start_request_id)
            finally:
                await engine.dispose()


if __name__ == "__main__":
    unittest.main()
