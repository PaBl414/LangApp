"""Optional lexical lookup: a missing entry is never proof of an invalid word."""
import asyncio
import html
import logging
import os
import re
from collections import OrderedDict
from dataclasses import dataclass
from time import monotonic
from urllib.parse import quote

import httpx

from .grading import clean_text, normalize_answer

log = logging.getLogger("langapp.dictionary")

# English Wiktionary separates languages by level-two headings. A Chinese
# heading alone cannot confirm a specifically Cantonese (yue) entry.
WIKTIONARY_LANGUAGES = {
    "en": {"English"}, "zh": {"Chinese"}, "hi": {"Hindi"}, "es": {"Spanish"},
    "fr": {"French"}, "ar": {"Arabic"}, "bn": {"Bengali"}, "pt": {"Portuguese"},
    "ru": {"Russian"}, "ur": {"Urdu"}, "id": {"Indonesian"}, "de": {"German"},
    "ja": {"Japanese"}, "sw": {"Swahili"}, "mr": {"Marathi"}, "te": {"Telugu"},
    "tr": {"Turkish"}, "ta": {"Tamil"}, "vi": {"Vietnamese"}, "ko": {"Korean"},
    "it": {"Italian"}, "th": {"Thai"}, "gu": {"Gujarati"}, "fa": {"Persian"},
    "pl": {"Polish"}, "uk": {"Ukrainian"}, "ml": {"Malayalam"}, "kn": {"Kannada"},
    "or": {"Odia", "Oriya"}, "my": {"Burmese"}, "pa": {"Punjabi"}, "ro": {"Romanian"},
    "nl": {"Dutch"}, "az": {"Azerbaijani"}, "el": {"Greek"}, "cs": {"Czech"},
    "hu": {"Hungarian"}, "sv": {"Swedish"}, "he": {"Hebrew"}, "da": {"Danish"},
    "fi": {"Finnish"}, "no": {"Norwegian", "Norwegian Bokmål", "Norwegian Nynorsk"},
    "sk": {"Slovak"}, "bg": {"Bulgarian"}, "hr": {"Croatian"}, "sr": {"Serbian"},
    "lt": {"Lithuanian"}, "lv": {"Latvian"}, "et": {"Estonian"},
}


def dictionary_enabled() -> bool:
    return os.getenv("LANGAPP_DICTIONARY_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class LookupResult:
    status: str
    source: str = "none"
    matched_word: str | None = None
    suggestions: tuple[str, ...] = ()

    def response(self, lang: str, word: str) -> dict:
        return {"status": self.status, "exists": self.status == "found", "source": self.source,
                "lang": lang, "word": word, "matched_word": self.matched_word, "suggestions": list(self.suggestions)}


class DictionaryLookup:
    """Bounded process-local TTL cache, shared in-flight lookups and a total deadline."""
    def __init__(self):
        self.cache: OrderedDict[tuple[str, str], tuple[float, LookupResult]] = OrderedDict()
        self.inflight: dict[tuple[str, str], asyncio.Task] = {}
        self.slots = asyncio.Semaphore(8)
        self.suggestion_cache: OrderedDict[tuple[str, str], tuple[float, LookupResult]] = OrderedDict()
        self.suggestion_inflight: dict[tuple[str, str], asyncio.Task] = {}

    def remember(self, key: tuple[str, str], result: LookupResult) -> None:
        ttl = {"found": 21600, "not_found": 300}.get(result.status, 15)
        self.cache[key] = (monotonic() + ttl, result)
        self.cache.move_to_end(key)
        while len(self.cache) > 1024:
            self.cache.popitem(last=False)

    async def suggest(self, lang: str, prefix: str) -> LookupResult:
        if not dictionary_enabled():
            return LookupResult("disabled")
        if lang not in WIKTIONARY_LANGUAGES:
            return LookupResult("unsupported")
        prefix = clean_text(prefix)
        if len(prefix) < 2:
            return LookupResult("not_found")
        key = (lang, prefix)
        cached = self.suggestion_cache.get(key)
        if cached and cached[0] > monotonic():
            self.suggestion_cache.move_to_end(key)
            return cached[1]
        task = self.suggestion_inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._suggest_and_cache(key))
            self.suggestion_inflight[key] = task
        return await asyncio.shield(task)

    async def _suggest_and_cache(self, key: tuple[str, str]) -> LookupResult:
        try:
            try:
                result = await asyncio.wait_for(self._suggest(*key), timeout=8.0)
            except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError):
                result = LookupResult("unavailable")
            self.suggestion_cache[key] = (monotonic() + (60 if result.status == "found" else 15), result)
            self.suggestion_cache.move_to_end(key)
            while len(self.suggestion_cache) > 512:
                self.suggestion_cache.popitem(last=False)
            return result
        finally:
            self.suggestion_inflight.pop(key, None)

    async def _suggest(self, lang: str, prefix: str) -> LookupResult:
        user_agent = os.getenv("LANGAPP_DICTIONARY_USER_AGENT", "LangApp/1.0 (https://github.com/PaBl414/LangApp)")
        async with httpx.AsyncClient(timeout=3.0, headers={"User-Agent": user_agent}) as client:
            items = None
            # Prefer the selected language edition's ranking rather than English
            # popularity for every language. Codes come from the fixed allowlist.
            endpoints = dict.fromkeys([f"https://{lang}.wiktionary.org/w/api.php", "https://en.wiktionary.org/w/api.php"])
            for endpoint in endpoints:
                try:
                    async with self.slots:
                        response = await client.get(endpoint, params={
                            "action": "query", "list": "prefixsearch", "pssearch": prefix,
                            "psprofile": "strict", "psnamespace": 0, "pslimit": 8,
                            "format": "json", "formatversion": 2,
                        })
                    response.raise_for_status()
                    data = response.json()
                    query = data.get("query") if isinstance(data, dict) else None
                    found = query.get("prefixsearch") if isinstance(query, dict) else None
                    if isinstance(found, list):
                        items = found
                        if items:
                            break
                except (httpx.HTTPError, ValueError, TypeError):
                    continue
            if not isinstance(items, list):
                return LookupResult("unavailable")
            candidates = []
            for item in items[:8]:
                title = item.get("title") if isinstance(item, dict) else None
                if (not isinstance(title, str) or item.get("ns") != 0 or not 1 <= len(title) <= 128
                        or clean_text(title) != title or title == prefix
                        or not normalize_answer(title).startswith(normalize_answer(prefix))):
                    continue
                if title not in candidates:
                    candidates.append(title)

            async def validate(title: str) -> LookupResult:
                cached = self.cached(lang, title)
                if cached is not None and cached.status == "found":
                    return cached
                async with self.slots:
                    result = await self._wiktionary(client, lang, title)
                if result.status == "found":
                    self.remember((lang, title), result)
                return result

            results = await asyncio.gather(*(validate(title) for title in candidates))
            suggestions, seen = [], set()
            for title, result in zip(candidates, results):
                key = normalize_answer(title)
                if result.status == "found" and key not in seen:
                    suggestions.append(title)
                    seen.add(key)
            if suggestions:
                return LookupResult("found", "wiktionary", suggestions=tuple(suggestions[:5]))
            return LookupResult("unavailable" if any(result.status == "unavailable" for result in results) else "not_found")

    def cached(self, lang: str, word: str) -> LookupResult | None:
        key = (lang, clean_text(word))
        entry = self.cache.get(key)
        if entry is None:
            return None
        expires, result = entry
        if expires <= monotonic():
            del self.cache[key]
            return None
        self.cache.move_to_end(key)
        return result

    def confirmed(self, lang: str, word: str) -> bool:
        result = self.cached(lang, word) if dictionary_enabled() else None
        return result is not None and result.status == "found"

    async def check(self, lang: str, word: str) -> LookupResult:
        if not dictionary_enabled():
            return LookupResult("disabled")
        if lang not in WIKTIONARY_LANGUAGES:
            return LookupResult("unsupported")
        word = clean_text(word)
        cached = self.cached(lang, word)
        if cached is not None:
            return cached
        key = (lang, word)
        task = self.inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._check_and_cache(key))
            self.inflight[key] = task
        return await asyncio.shield(task)

    async def _check_and_cache(self, key: tuple[str, str]) -> LookupResult:
        try:
            try:
                result = await asyncio.wait_for(self._lookup(*key), timeout=8.0)
            except (TimeoutError, httpx.HTTPError, ValueError, TypeError, KeyError):
                log.info("Dictionary lookup temporarily unavailable (%s)", key[0])
                result = LookupResult("unavailable")
            self.remember(key, result)
            return result
        finally:
            self.inflight.pop(key, None)

    async def _lookup(self, lang: str, word: str) -> LookupResult:
        async with self.slots:
            user_agent = os.getenv("LANGAPP_DICTIONARY_USER_AGENT", "LangApp/1.0 (https://github.com/PaBl414/LangApp)")
            async with httpx.AsyncClient(timeout=3.0, headers={"User-Agent": user_agent}) as client:
                unavailable = False
                if lang == "en":
                    result = await self._english(client, word)
                    if result.status == "found":
                        return result
                    unavailable = result.status == "unavailable"
                # Only spelling-case variants; preserve accents and whole phrases.
                variants = dict.fromkeys([word, word.lower(), word[:1].upper() + word[1:].lower()])
                for variant in variants:
                    result = await self._wiktionary(client, lang, variant)
                    if result.status == "found":
                        return result
                    if result.status == "unavailable":
                        unavailable = True
                        break
                return LookupResult("unavailable" if unavailable else "not_found")

    @staticmethod
    async def _english(client: httpx.AsyncClient, word: str) -> LookupResult:
        try:
            response = await client.get("https://api.dictionaryapi.dev/api/v2/entries/en/" + quote(word.lower(), safe=""))
            if response.status_code == 404:
                data = response.json()
                return LookupResult("not_found" if isinstance(data, dict) and data.get("title") == "No Definitions Found" else "unavailable")
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list) or not data:
                return LookupResult("unavailable")
            for entry in data:
                if (isinstance(entry, dict) and isinstance(entry.get("word"), str)
                        and normalize_answer(entry["word"]) == normalize_answer(word)
                        and isinstance(entry.get("meanings"), list) and entry["meanings"]):
                    return LookupResult("found", "dictionaryapi", entry["word"])
            return LookupResult("unavailable")
        except (httpx.HTTPError, ValueError, TypeError):
            return LookupResult("unavailable")

    @staticmethod
    async def _wiktionary(client: httpx.AsyncClient, lang: str, word: str) -> LookupResult:
        try:
            response = await client.get("https://en.wiktionary.org/w/api.php", params={
                "action": "parse", "page": word, "prop": "tocdata", "format": "json", "formatversion": 2,
            })
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                return LookupResult("unavailable")
            if "error" in data:
                error = data["error"]
                return LookupResult("not_found" if isinstance(error, dict) and error.get("code") == "missingtitle" else "unavailable")
            parsed = data.get("parse")
            if not isinstance(parsed, dict) or not isinstance(parsed.get("title"), str):
                return LookupResult("unavailable")
            toc = parsed.get("tocdata")
            sections = toc.get("sections") if isinstance(toc, dict) else None
            if not isinstance(sections, list) or any(not isinstance(section, dict) for section in sections):
                return LookupResult("unavailable")
            if normalize_answer(parsed["title"]) != normalize_answer(word):
                return LookupResult("not_found")
            for section in sections:
                if section.get("hLevel") not in (2, "2"):
                    continue
                line = section.get("line")
                if not isinstance(line, str):
                    return LookupResult("unavailable")
                language = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
                if language in WIKTIONARY_LANGUAGES[lang]:
                    return LookupResult("found", "wiktionary", parsed["title"])
            return LookupResult("not_found")
        except (httpx.HTTPError, ValueError, TypeError):
            return LookupResult("unavailable")


dictionary = DictionaryLookup()
