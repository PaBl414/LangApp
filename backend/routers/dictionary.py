"""Optional dictionary checks: missing entries never block saving vocabulary."""
import asyncio
from fastapi import APIRouter, HTTPException, Query

from ..dictionary_service import WIKTIONARY_LANGUAGES, dictionary, dictionary_enabled
from ..grading import clean_text

router = APIRouter(prefix="/api/dictionary", tags=["dictionary"])


@router.get("/config")
async def configuration():
    return {"enabled": dictionary_enabled(), "languages": sorted(WIKTIONARY_LANGUAGES)}


@router.get("/check")
async def check_word(
    lang: str = Query(..., min_length=2, max_length=8),
    word: str = Query(..., min_length=1, max_length=128),
    suggest: bool = Query(default=False),
):
    word = clean_text(word)
    if not word:
        raise HTTPException(400, "Puste słowo.")
    lang = lang.strip().lower()
    if suggest:
        result, completions = await asyncio.gather(dictionary.check(lang, word), dictionary.suggest(lang, word))
        response = result.response(lang, word)
        response.update(suggestions=list(completions.suggestions), suggestions_status=completions.status)
        return response
    return (await dictionary.check(lang, word)).response(lang, word)
