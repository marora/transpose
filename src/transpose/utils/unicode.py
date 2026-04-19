"""Unicode normalization helpers for Indic script text."""

from __future__ import annotations

import unicodedata


def normalize_unicode(text: str) -> str:
    """Apply NFC normalization to ensure consistent Unicode representation.

    Devanagari and Gurmukhi composed characters can arrive in multiple
    equivalent byte sequences (NFD vs NFC).  NFC is the canonical form
    expected by fonts, search, and rendering engines.
    """
    return unicodedata.normalize("NFC", text) if text else text
