"""Atomic quick-entry regressions using temporary DBs and in-process requests."""
import asyncio
from datetime import date
from unittest.mock import patch

from sqlalchemy import select

from backend.models import UserWord, WordReview
from test_accounts_sessions_data import APITestCase


class QuickWordTests(APITestCase):
    async def prepare(self):
        await self.register()
        response = await self.client.post("/api/user/languages", json={"language_id": 1})
        self.assertEqual(response.status_code, 200, response.text)

    async def send(self, pairs, language_id=1):
        return await self.client.post(f"/api/user/languages/{language_id}/words/import", json={
            "words": [{"word": word, "translation_pl": translation} for word, translation in pairs],
        })

    async def words(self):
        response = await self.client.get("/api/user/languages/1/words")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["words"]

    async def test_normalization_duplicates_and_lost_response_retry(self):
        await self.prepare()
        pairs = [(" cafe\u0301 ", " kawiarnia "), ("CAFÉ", "KAWIARNIA"), ("house", " dom   rodzinny ")]
        with patch("backend.routers.dictionary.httpx.AsyncClient", side_effect=AssertionError("Quick entry must not call third-party APIs")):
            first = await self.send(pairs)
            retry = await self.send(pairs)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual((first.json()["added"], first.json()["skipped"]), (2, 1))
        self.assertEqual((retry.json()["added"], retry.json()["skipped"]), (0, 3))
        self.assertEqual(first.json()["words"], retry.json()["words"])
        words = await self.words()
        self.assertEqual({(w["word"], w["translation_pl"]) for w in words}, {("café", "kawiarnia"), ("house", "dom rodzinny")})
        self.assertTrue(all(not word["is_valid"] for word in words))

    async def test_conflicting_existing_or_in_batch_translation_rolls_back_entire_list(self):
        await self.prepare()
        await self.send([("cat", "kot")])
        for pairs in [[("dog", "pies"), ("CAT", "pies")], [("new", "nowy"), ("NEW", "inne")]]:
            response = await self.send(pairs)
            self.assertEqual(response.status_code, 409, response.text)
            self.assertIn("Nie zapisano", response.json()["detail"])
            self.assertEqual([word["word"] for word in await self.words()], ["cat"])

    async def test_failed_commit_is_atomic_and_retry_succeeds(self):
        await self.prepare()
        from backend.routers.languages import AsyncSession
        async def fail_after_flush(db):
            await db.flush()
            raise RuntimeError("simulated disk failure after inserting the batch")
        with patch.object(AsyncSession, "commit", new=fail_after_flush):
            response = await self.send([("cat", "kot"), ("dog", "pies")])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(await self.words(), [])
        self.assertEqual((await self.send([("cat", "kot"), ("dog", "pies")])).json()["added"], 2)

    async def test_identical_import_preserves_aliases_verification_and_review_state(self):
        await self.prepare()
        added = (await self.send([("hello", "cześć")])).json()["words"][0]
        async with self.sessions() as db:
            word = await db.get(UserWord, added["id"])
            word.translation_alternatives = ["witaj"]
            word.word_alternatives = ["hi"]
            word.is_valid = True
            db.add(WordReview(user_id=1, word_id=word.id, language_id=1,
                direction="lang_to_pl", attempts=3, correct_answers=2, consecutive_correct=1,
                due_on=date(2030, 1, 1), last_correct=True))
            await db.commit()
        response = await self.send([("HELLO", "CZEŚĆ")])
        self.assertEqual(response.status_code, 200, response.text)
        word = response.json()["words"][0]
        self.assertEqual(word["word"], "hello")
        self.assertEqual(word["translation_alternatives"], ["witaj"])
        self.assertEqual(word["word_alternatives"], ["hi"])
        self.assertTrue(word["is_valid"])
        async with self.sessions() as db:
            review = (await db.execute(select(WordReview))).scalar_one()
            self.assertEqual((review.attempts, review.correct_answers, review.due_on), (3, 2, date(2030, 1, 1)))

    async def test_concurrent_imports_and_single_word_entry_do_not_create_duplicates(self):
        await self.prepare()
        responses = await asyncio.gather(
            self.send([("cat", "kot")]), self.send([("CAT", "kot")]),
            self.client.post("/api/user/languages/1/words", json={"word": "Cat", "translation_pl": "kot"}),
        )
        self.assertTrue(all(response.status_code in {200, 409} for response in responses), [response.text for response in responses])
        self.assertEqual(len(await self.words()), 1)

    async def test_strict_validation_and_batch_size_boundaries(self):
        await self.prepare()
        url = "/api/user/languages/1/words/import"
        invalid = [[], [{"word": " ", "translation_pl": "kot"}],
            [{"word": "cat", "translation_pl": 12}], [{"word": "x" * 129, "translation_pl": "kot"}],
            [{"word": "cat", "translation_pl": "kot", "is_valid": True}],
            [{"word": "cat", "translation_pl": "kot"}] * 101]
        for entries in invalid:
            with self.subTest(entries=str(entries)[:120]):
                response = await self.client.post(url, json={"words": entries})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(await self.words(), [])
        response = await self.send([(f"word{i}", f"słowo{i}") for i in range(100)])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["added"], 100)
        self.assertEqual(len(await self.words()), 100)

    async def test_owner_language_and_authentication_are_enforced(self):
        self.assertEqual((await self.send([("cat", "kot")])).status_code, 401)
        await self.prepare()
        self.assertEqual((await self.send([("cat", "kot")], language_id=2)).status_code, 404)
        await self.send([("cat", "kot")])
        first_token = dict(self.client.cookies)
        self.client.cookies.clear()
        await self.register("second")
        self.assertEqual((await self.send([("dog", "pies")])).status_code, 404)
        await self.client.post("/api/user/languages", json={"language_id": 1})
        self.assertEqual((await self.send([("cat", "pies")])).status_code, 200)
        self.client.cookies.clear()
        self.client.cookies.update(first_token)
        self.assertEqual([(word["word"], word["translation_pl"]) for word in await self.words()], [("cat", "kot")])
