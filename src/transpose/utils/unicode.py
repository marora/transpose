"""Unicode normalization helpers for Indic script text."""

from __future__ import annotations

import re
import unicodedata

_LATIN_ONLY_RE = re.compile(r"^[A-Za-z\s\-']+$")
_LATIN_CHARS_RE = re.compile(r"[A-Za-z]")


def normalize_unicode(text: str) -> str:
    """Apply NFC normalization to ensure consistent Unicode representation.

    Devanagari and Gurmukhi composed characters can arrive in multiple
    equivalent byte sequences (NFD vs NFC).  NFC is the canonical form
    expected by fonts, search, and rendering engines.
    """
    return unicodedata.normalize("NFC", text) if text else text


def is_latin_only(text: str) -> bool:
    """Return True if text contains only Latin characters, spaces, hyphens, apostrophes."""
    return bool(text and _LATIN_ONLY_RE.match(text))


def strip_latin_from_indic(text: str) -> str:
    """Remove stray Latin characters from an Indic script string.

    LLM/OCR sometimes injects Latin chars (e.g. 'L यान' instead of 'ध्यान').
    Returns the cleaned string with Latin chars removed and whitespace collapsed.
    """
    if not text:
        return text
    cleaned = _LATIN_CHARS_RE.sub("", text).strip()
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned
