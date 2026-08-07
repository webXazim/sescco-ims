from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_NON_DIGIT = re.compile(r"\D+")


def normalize_text(value: str | None) -> str:
    """Normalize user-entered identity text while preserving multilingual content."""
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    return normalized.casefold()


def clean_display_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return _WHITESPACE.sub(" ", normalized).strip()


def normalize_phone(value: str | None) -> str:
    """Return digits-only phone identity; 00-prefixed international numbers match + numbers."""
    digits = _NON_DIGIT.sub("", unicodedata.normalize("NFKC", value or ""))
    if digits.startswith("00"):
        digits = digits[2:]
    return digits
