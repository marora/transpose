"""Manuscript and document structure models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass
class Chapter:
    """A chapter in the assembled manuscript."""

    number: int
    title: str
    content_html: str


@dataclass
class Manuscript:
    """Assembled manuscript ready for export."""

    book_id: UUID
    title: str
    chapters: list[Chapter]
    glossary_id: UUID
    table_of_contents: list[dict] = field(default_factory=list)
    author: str | None = None
    metadata: dict = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
