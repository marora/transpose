"""Book and Page data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from transpose.models.enums import BookStatus, SourceLanguage


@dataclass
class Book:
    """A book registered in the pipeline."""

    title: str
    source_language: SourceLanguage
    source_hash: str
    source_blob_uri: str
    id: UUID = field(default_factory=uuid4)
    author: str | None = None
    status: BookStatus = BookStatus.INGESTED
    page_count: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Page:
    """OCR result for a single page."""

    book_id: UUID
    page_number: int
    raw_text: str
    confidence: float = 1.0
    needs_review: bool = False
    ocr_metadata: dict = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
