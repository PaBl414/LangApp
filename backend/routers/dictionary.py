"""
Walidacja słów przez darmowe API (bez klucza).
- Datamuse: https://api.datamuse.com/sug?s=...  (sugestie)
- Free Dictionary API: https://api.dictionaryapi.dev/api/v2/entries/en/{word}  (istnienie)
"""
import logging
import httpx
from fastapi import APIRouter, HTTPException, Query

log = logging.getLogger("langapp.dictionary")
router = APIRouter(prefix="/api/dictionary", tags=["dictionary"])

# Kody języków obsługiwane przez Datamuse (angielski + hiszpański)
DATAMUSE_LANGS = {"en", "es"}


@router.get("/check")
async def check_word(
    lang: str = Query(..., min_length=2, max_length=8),
    word: str = Query(..., min_length=1, max_length=64),
):
    """
    Sprawdza istnienie słowa i zwraca sugestie podobnych.
    Zwraca: { exists: bool, suggestions: [str], source: str }
    """
    word = word.strip().lower()
    if not word:
        raise HTTPException(400, "Puste słowo.")

    exists = False
    suggestions: list[str] = []
    source = "none"

    async with httpx.AsyncClient(timeout=6.0) as client:
        # 1) Free Dictionary API — tylko dla angielskiego
        if lang == "en":
            try:
                r = await client.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
                if r.status_code == 200:
                    exists = True
                    source = "dictionaryapi"
                elif r.status_code == 404:
                    exists = False
            except Exception as e:
                log.warning("Free Dictionary API error: %s", e)

        # 2) Datamuse — sugestie (i dodatkowa walidacja dla en/es)
        if lang in DATAMUSE_LANGS:
            try:
                r = await client.get(
                    "https://api.datamuse.com/sug",
                    params={"s": word, "max": 5},
                )
                if r.status_code == 200:
                    items = r.json() or []
                    cand = [it["word"] for it in items if "word" in it]
                    # Jeśli samo słowo jest na liście sugestii — istnieje
                    if word in [c.lower() for c in cand]:
                        exists = True
                        if source == "none":
                            source = "datamuse"
                    # Sugestie: odfiltruj dokładnie to samo słowo
                    suggestions = [c for c in cand if c.lower() != word][:3]
            except Exception as e:
                log.warning("Datamuse error: %s", e)

    # Jeśli API nic nie zwróciło, ale słowo ma sens — spróbujmy
    # dopasować lokalnie po podobieństwie do sugestii (już mamy suggestions)
    if not exists and suggestions:
        # słowo istnieje "prawdopodobnie" — ale nie potwierdzone
        source = source if source != "none" else "suggest-only"

    return {
        "exists": exists,
        "suggestions": suggestions,
        "source": source,
        "lang": lang,
        "word": word,
    }