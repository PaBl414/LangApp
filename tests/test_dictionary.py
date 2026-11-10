"""Lexical checks with mocked providers; no external calls or TCP listeners."""
import asyncio
import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.dictionary_service import DictionaryLookup, LookupResult
from test_accounts_sessions_data import APITestCase


def wiki(title, language, level=2):
    return {"parse": {"title": title, "tocdata": {"sections": [{"hLevel": level, "line": language}]}}}


class DictionaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = DictionaryLookup()
        self.environment = patch.dict(os.environ, {"LANGAPP_DICTIONARY_ENABLED": "1"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    async def lookup(self, lang, word, handler):
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        try:
            with patch("backend.dictionary_service.httpx.AsyncClient", return_value=client):
                return await self.service.check(lang, word)
        finally:
            await client.aclose()

    async def test_english_requires_exact_entry_and_falls_back_after_provider_failure(self):
        calls = []
        def handler(request):
            calls.append(request)
            if request.url.host == "api.dictionaryapi.dev":
                return httpx.Response(503, text="unavailable")
            return httpx.Response(200, json=wiki("hello", "English"))
        result = await self.lookup("en", "hello", handler)
        self.assertEqual((result.status, result.source), ("found", "wiktionary"))
        self.assertEqual(len(calls), 2)

    async def test_english_primary_short_circuits_other_providers(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json=[{"word": "hello", "meanings": [{"partOfSpeech": "interjection"}]}])
        result = await self.lookup("en", "HELLO", handler)
        self.assertEqual((result.status, result.source), ("found", "dictionaryapi"))
        self.assertEqual(len(calls), 1)

    async def test_wrong_language_or_nested_language_heading_cannot_confirm_word(self):
        for level, language in [(2, "English"), (3, "Spanish")]:
            with self.subTest(level=level, language=language):
                self.service = DictionaryLookup()
                result = await self.lookup("es", "hello", lambda request: httpx.Response(200, json=wiki(request.url.params["page"], language, level)))
                self.assertEqual(result.status, "not_found")

    async def test_capitalization_and_accents_are_preserved(self):
        requested = []
        def handler(request):
            word = request.url.params["page"]
            requested.append(word)
            if word == "Überraschung":
                return httpx.Response(200, json=wiki(word, "German"))
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        result = await self.lookup("de", "u\u0308berraschung", handler)
        self.assertEqual((result.status, result.matched_word), ("found", "Überraschung"))
        self.assertEqual(requested, ["überraschung", "Überraschung"])

    async def test_whole_phrases_do_not_get_validated_by_individual_tokens(self):
        requested = []
        def handler(request):
            requested.append(request.url.params["page"])
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        self.assertEqual((await self.lookup("de", "guten unknown", handler)).status, "not_found")
        self.assertTrue(all(" " in word for word in requested))

    async def test_rate_limit_html_timeout_and_malformed_data_mean_unavailable(self):
        cases = [lambda request: httpx.Response(429), lambda request: httpx.Response(200, text="<html>gateway</html>"),
            lambda request: httpx.Response(200, json={"parse": {"title": "hola"}}),
            lambda request: httpx.Response(200, json={"error": {"code": "ratelimited"}}),
            lambda request: httpx.Response(200, json={"parse": {"title": "hola", "tocdata": {"sections": [42]}}})]
        for handler in cases:
            self.service = DictionaryLookup()
            self.assertEqual((await self.lookup("es", "hola", handler)).status, "unavailable")
        def timeout(request):
            raise httpx.ReadTimeout("simulated", request=request)
        self.service = DictionaryLookup()
        self.assertEqual((await self.lookup("es", "hola", timeout)).status, "unavailable")

    async def test_suggestions_or_different_titles_never_confirm_exact_input(self):
        result = await self.lookup("es", "holaa", lambda request: httpx.Response(200, json=wiki("hola", "Spanish")))
        self.assertEqual(result.status, "not_found")

    async def test_cache_deadlines_size_and_shared_inflight_work(self):
        async def slow(*args):
            await asyncio.sleep(0.01)
            return LookupResult("found", "wiktionary", "hola")
        with patch.object(self.service, "_lookup", new=AsyncMock(side_effect=slow)) as lookup:
            first, second = await asyncio.gather(self.service.check("es", "hola"), self.service.check("es", "hola"))
            self.assertEqual(first, second)
            await self.service.check("es", "hola")
            self.assertEqual(lookup.await_count, 1)
            self.service.cache[("es", "hola")] = (0, first)
            await self.service.check("es", "hola")
            self.assertEqual(lookup.await_count, 2)
        with patch.object(self.service, "_lookup", new=AsyncMock(return_value=LookupResult("not_found"))):
            for i in range(1025):
                await self.service.check("es", str(i))
        self.assertEqual(len(self.service.cache), 1024)
        self.assertNotIn(("es", "hola"), self.service.cache)

    async def test_disabled_and_unsupported_do_not_contact_any_provider(self):
        with patch.object(self.service, "_lookup", new=AsyncMock()) as lookup:
            self.assertEqual((await self.service.check("yue", "字")).status, "unsupported")
            with patch.dict(os.environ, {"LANGAPP_DICTIONARY_ENABLED": "0"}):
                self.assertEqual((await self.service.check("en", "hello")).status, "disabled")
                self.assertFalse(self.service.confirmed("en", "hello"))
            lookup.assert_not_awaited()

    async def test_cancelled_caller_does_not_cancel_other_waiters(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def slow(*args):
            started.set()
            await release.wait()
            return LookupResult("found", "wiktionary", "hola")
        with patch.object(self.service, "_lookup", side_effect=slow):
            first = asyncio.create_task(self.service.check("es", "hola"))
            await started.wait()
            second = asyncio.create_task(self.service.check("es", "hola"))
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            release.set()
            self.assertEqual((await second).status, "found")
        self.assertEqual(self.service.inflight, {})

    async def test_completions_require_prefix_namespace_and_selected_language(self):
        checked = []
        def handler(request):
            if request.url.params.get("action") == "query":
                self.assertEqual(request.url.params["psprofile"], "strict")
                return httpx.Response(200, json={"query": {"prefixsearch": [
                    {"ns": 0, "title": "hello"}, {"ns": 0, "title": "helado"},
                    {"ns": 0, "title": "help"}, {"ns": 14, "title": "hel-category"},
                    {"ns": 0, "title": "unrelated"}, {"ns": 0, "title": "hello"},
                ]}})
            title = request.url.params["page"]
            checked.append(title)
            return httpx.Response(200, json=wiki(title, "Spanish" if title == "helado" else "English"))
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("backend.dictionary_service.httpx.AsyncClient", return_value=client):
            result = await self.service.suggest("en", "hel")
        self.assertEqual(result.suggestions, ("hello", "help"))
        self.assertCountEqual(checked, ["hello", "helado", "help"])
        self.assertTrue(self.service.confirmed("en", "hello"))
        self.assertIsNone(self.service.cached("en", "hel"))

    async def test_suggestions_do_not_strip_accents_or_confirm_missing_pages(self):
        def handler(request):
            if request.url.params.get("action") == "query":
                return httpx.Response(200, json={"query": {"prefixsearch": [
                    {"ns": 0, "title": "cafe"}, {"ns": 0, "title": "cafétéria"},
                    {"ns": 0, "title": "caféine"},
                ]}})
            if request.url.params["page"] == "cafétéria":
                return httpx.Response(200, json=wiki("cafétéria", "French"))
            return httpx.Response(200, json={"error": {"code": "missingtitle"}})
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("backend.dictionary_service.httpx.AsyncClient", return_value=client):
            result = await self.service.suggest("fr", "café")
        self.assertEqual(result.suggestions, ("cafétéria",))

    async def test_suggestion_cache_concurrency_disable_and_failure(self):
        async def slow(*args):
            await asyncio.sleep(0.01)
            return LookupResult("found", "wiktionary", suggestions=("hello",))
        with patch.object(self.service, "_suggest", new=AsyncMock(side_effect=slow)) as lookup:
            first, second = await asyncio.gather(self.service.suggest("en", "hel"), self.service.suggest("en", "hel"))
            self.assertEqual(first, second)
            await self.service.suggest("en", "hel")
            lookup.assert_awaited_once()
            with patch.dict(os.environ, {"LANGAPP_DICTIONARY_ENABLED": "0"}):
                self.assertEqual((await self.service.suggest("en", "hel")).status, "disabled")
            self.assertEqual((await self.service.suggest("en", "h")).suggestions, ())
            self.assertEqual((await self.service.suggest("yue", "你好")).status, "unsupported")
            lookup.assert_awaited_once()
        with patch.object(self.service, "_suggest", new=AsyncMock(side_effect=httpx.ReadTimeout("offline"))):
            result = await self.service.suggest("en", "other")
            self.assertEqual((result.status, result.suggestions), ("unavailable", ()))

    async def test_suggestion_limit_and_no_negative_language_validation(self):
        def handler(request):
            if request.url.params.get("action") == "query":
                return httpx.Response(200, json={"query": {"prefixsearch": [{"ns": 0, "title": "he" + str(i)} for i in range(8)]}})
            return httpx.Response(200, json=wiki(request.url.params["page"], "English"))
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("backend.dictionary_service.httpx.AsyncClient", return_value=client):
            result = await self.service.suggest("en", "he")
        self.assertEqual(len(result.suggestions), 5)

    async def test_locale_search_falls_back_but_language_is_always_verified(self):
        hosts = []
        def handler(request):
            hosts.append(request.url.host)
            if request.url.host == "fr.wiktionary.org":
                return httpx.Response(503)
            if request.url.params.get("action") == "query":
                return httpx.Response(200, json={"query": {"prefixsearch": [{"ns": 0, "title": "bonjour"}]}})
            return httpx.Response(200, json=wiki("bonjour", "French"))
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with patch("backend.dictionary_service.httpx.AsyncClient", return_value=client):
            result = await self.service.suggest("fr", "bon")
        self.assertEqual(result.suggestions, ("bonjour",))
        self.assertEqual(hosts, ["fr.wiktionary.org", "en.wiktionary.org", "en.wiktionary.org"])


class DictionaryAPITests(APITestCase):
    async def test_suggestions_are_separate_from_exact_word_confirmation(self):
        with patch("backend.routers.dictionary.dictionary.check", new=AsyncMock(return_value=LookupResult("not_found"))), patch("backend.routers.dictionary.dictionary.suggest", new=AsyncMock(return_value=LookupResult("found", "wiktionary", suggestions=("hello", "help")))):
            response = await self.client.get("/api/dictionary/check", params={"lang": "en", "word": "hel", "suggest": "true"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["suggestions"], ["hello", "help"])
        self.assertFalse(response.json()["exists"])
        self.assertEqual(response.json()["status"], "not_found")
        self.assertEqual(response.json()["suggestions_status"], "found")

    async def test_structured_statuses_and_server_disable(self):
        with patch.dict(os.environ, {"LANGAPP_DICTIONARY_ENABLED": "0"}), patch("backend.dictionary_service.httpx.AsyncClient", side_effect=AssertionError("No external request allowed")):
            self.assertFalse((await self.client.get("/api/dictionary/config")).json()["enabled"])
            response = await self.client.get("/api/dictionary/check", params={"lang": "en", "word": "hello"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "disabled")
            self.assertFalse(response.json()["exists"])
            response = await self.client.get("/api/dictionary/check", params={"lang": "en", "word": "hel", "suggest": "true"})
            self.assertEqual(response.json()["suggestions_status"], "disabled")
            self.assertEqual(response.json()["suggestions"], [])
        response = await self.client.get("/api/dictionary/check", params={"lang": "en", "word": " "})
        self.assertEqual(response.status_code, 400)

    async def test_client_cannot_mark_word_verified_and_save_never_calls_provider(self):
        await self.register()
        await self.client.post("/api/user/languages", json={"language_id": 1})
        with patch("backend.routers.languages.dictionary.confirmed", return_value=False), patch("backend.dictionary_service.httpx.AsyncClient", side_effect=AssertionError("Saving must not contact providers")):
            response = await self.client.post("/api/user/languages/1/words", json={"word": "hello", "translation_pl": "cześć", "is_valid": True})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["word"]["is_valid"])
        with patch("backend.routers.languages.dictionary.confirmed", return_value=True):
            response = await self.client.post("/api/user/languages/1/words/import", json={"words": [{"word": "cat", "translation_pl": "kot"}]})
        self.assertTrue(response.json()["words"][0]["is_valid"])
