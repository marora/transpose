"""Unicode normalization helpers for Indic script text."""

from __future__ import annotations

import re
import unicodedata

_LATIN_ONLY_RE = re.compile(r"^[A-Za-z\s\-']+$")
_LATIN_CHARS_RE = re.compile(r"[A-Za-z]")

# Unicode block ranges
_DEVANAGARI_RANGE = (0x0900, 0x097F)
_GURMUKHI_RANGE = (0x0A00, 0x0A7F)

# Matches isolated ASCII letters/digits (1-2 chars) surrounded by Devanagari.
# Lookbehind: Devanagari char; match: 1-2 ASCII alphanumeric; lookahead: Devanagari char.
_ISOLATED_ASCII_IN_DEVANAGARI_RE = re.compile(
    r"(?<=[\u0900-\u097F])[A-Za-z0-9]{1,2}(?=[\u0900-\u097F])"
)

# Zero-width and control characters that are OCR noise (not legitimate Devanagari joiners).
# Keeps U+200D (ZWJ) which is valid in Devanagari conjuncts.
_OCR_CONTROL_CHARS_RE = re.compile(
    r"[\u200B\u200C\u200E\u200F\uFEFF\u00AD"
    r"\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]"
)

_NESTED_FAIL_MARKER_RE = re.compile(r"\[TRANSLATION FAILED[^\]]*\]")
_MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


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


def contains_gurmukhi(text: str) -> bool:
    """Return True if *text* contains any Gurmukhi-block codepoints (U+0A00–U+0A7F)."""
    if not text:
        return False
    lo, hi = _GURMUKHI_RANGE
    return any(lo <= ord(ch) <= hi for ch in text)


def contains_devanagari(text: str) -> bool:
    """Return True if *text* contains any Devanagari-block codepoints (U+0900–U+097F)."""
    if not text:
        return False
    lo, hi = _DEVANAGARI_RANGE
    return any(lo <= ord(ch) <= hi for ch in text)


def strip_gurmukhi(text: str) -> str:
    """Remove Gurmukhi-block characters from *text*, collapse whitespace."""
    if not text:
        return text
    lo, hi = _GURMUKHI_RANGE
    cleaned = "".join(ch for ch in text if not (lo <= ord(ch) <= hi))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def validate_script_for_language(text: str, language: str) -> bool:
    """Check that *text* uses the expected script for *language*.

    For Hindi (``"hindi"`` / ``"hi"``): expects Devanagari, rejects Gurmukhi.
    For Punjabi (``"punjabi"`` / ``"pa"``): expects Gurmukhi, rejects Devanagari.
    Returns True when valid (or when *text* is empty / Latin-only).
    """
    if not text or is_latin_only(text):
        return True

    lang = language.lower()
    if lang in ("hindi", "hi"):
        return not contains_gurmukhi(text)
    if lang in ("punjabi", "pa"):
        return not contains_devanagari(text)
    return True


def normalize_romanized_term(term: str) -> str:
    """Normalize a romanized term for fuzzy deduplication.

    Lowercases, strips trailing vowels (a/ah/ha), collapses hyphens/spaces.
    E.g. ``"bhairava"`` and ``"bhairav"`` both become ``"bhairav"``.
    """
    t = term.lower().strip()
    # Remove hyphens and spaces for comparison
    t = re.sub(r"[\s\-]+", "", t)
    # Strip common trailing vowel suffixes (longest first)
    for suffix in ("ha", "ah", "a"):
        if len(t) > 3 and t.endswith(suffix):
            t = t[: -len(suffix)]
            break
    return t


def clean_devanagari_ocr(text: str) -> str:
    """Clean garbled OCR output for Devanagari (Hindi) text.

    Applies the following normalizations in order:

    1. NFC Unicode normalization.
    2. Remove zero-width / control character noise (keeps ZWJ U+200D).
    3. Remove nested ``[TRANSLATION FAILED …]`` markers.
    4. Remove isolated ASCII digits/letters (1-2 chars) embedded between
       Devanagari characters — these are OCR artifacts.  Full English words
       (3+ contiguous ASCII letters) are preserved as intentional loanwords
       or proper nouns.
    5. Collapse duplicate whitespace.
    6. Strip leading/trailing whitespace on every line.

    The function is intentionally conservative: it only removes characters
    that are *very likely* OCR noise, never legitimate content.
    """
    if not text:
        return text

    # 1. NFC normalization
    text = unicodedata.normalize("NFC", text)

    # 2. Strip OCR control-character noise
    text = _OCR_CONTROL_CHARS_RE.sub("", text)

    # 3. Remove nested failure markers
    text = _NESTED_FAIL_MARKER_RE.sub("", text)

    # 4. Remove isolated ASCII (1-2 chars) between Devanagari characters
    text = _ISOLATED_ASCII_IN_DEVANAGARI_RE.sub("", text)

    # 5. Collapse multiple spaces / tabs (preserve newlines for structure)
    text = _MULTI_SPACE_RE.sub(" ", text)

    # 6. Strip each line and drop blank-only lines that result from cleanup
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)

    return text
