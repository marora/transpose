"""Glossary data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from transpose.models.enums import TermSource


@dataclass
class GlossaryEntry:
    """A single entry in the book glossary."""

    term: str
    original_script: str
    definition: str
    source: TermSource
    occurrence_count: int
    first_chapter: str | None = None
    needs_review: bool = False


@dataclass
class Glossary:
    """Aggregated glossary for a book."""

    book_id: UUID
    entries: list[GlossaryEntry] = field(default_factory=list)
    version: int = 1
    id: UUID = field(default_factory=uuid4)
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
