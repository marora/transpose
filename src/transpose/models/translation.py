"""Translation-related data models: Chunk, Translation, CulturalTerm."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from transpose.models.enums import SectionType, TermSource


@dataclass
class Chunk:
    """A translation-ready text segment."""

    book_id: UUID
    sequence: int
    source_text: str
    token_count: int
    page_start: int
    page_end: int
    section_type: SectionType = SectionType.PROSE
    chapter_ref: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ExtractedTerm:
    """A cultural term extracted during translation of a single chunk."""

    term: str
    original_script: str
    definition: str
    source: TermSource


@dataclass
class Translation:
    """Translation result for a single chunk."""

    chunk_id: UUID
    book_id: UUID
    translated_text: str
    model_version: str
    cultural_terms: list[ExtractedTerm] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: dict = field(default_factory=dict)
    error_type: str | None = None
    error_reason: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class CulturalTerm:
    """A cultural term aggregated at the book level."""

    book_id: UUID
    term: str
    definition: str
    original_script: str = ""
    source: TermSource = TermSource.SEED
    occurrence_count: int = 1
    first_chapter: str | None = None
    needs_review: bool = False
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
