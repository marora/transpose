"""Unicode normalization helpers for Indic script text."""

from __future__ import annotations

import re
import unicodedata

_LATIN_ONLY_RE = re.compile(r"^[A-Za-z\s\-']+$")


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
