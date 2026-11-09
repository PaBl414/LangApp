"""Explicit answer equivalence: Unicode NFC, whitespace and letter case only."""
import unicodedata


def clean_text(value: str) -> str:
    return unicodedata.normalize("NFC", " ".join(value.split()))


def normalize_answer(value: str) -> str:
    return clean_text(value).casefold()


def accepted_variants(primary: str, alternatives: list[str]) -> list[str]:
    variants, seen = [], set()
    for value in [primary, *alternatives]:
        cleaned = clean_text(value)
        key = normalize_answer(cleaned)
        if key and key not in seen:
            variants.append(cleaned)
            seen.add(key)
    return variants


def is_correct(given: str, expected: str, alternatives: list[str]) -> bool:
    value = normalize_answer(given)
    return bool(value) and any(value == normalize_answer(item) for item in [expected, *alternatives])
