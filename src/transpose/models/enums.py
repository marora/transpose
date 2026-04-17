"""Enumerations used across the Transpose pipeline."""

from enum import StrEnum


class BookStatus(StrEnum):
    """Lifecycle status of a book in the pipeline."""

    INGESTED = "ingested"
    OCR_COMPLETE = "ocr_complete"
    CHUNKED = "chunked"
    TRANSLATED = "translated"
    ASSEMBLED = "assembled"
    EXPORTED = "exported"
    FAILED = "failed"


class SourceLanguage(StrEnum):
    """Supported source languages."""

    HINDI = "hindi"
    PUNJABI = "punjabi"


class SectionType(StrEnum):
    """Structural type of a text chunk."""

    CHAPTER = "chapter"
    HEADING = "heading"
    VERSE = "verse"
    PROSE = "prose"


class TermSource(StrEnum):
    """How a cultural term was identified."""

    SEED = "seed"
    LLM_DETECTED = "llm_detected"
