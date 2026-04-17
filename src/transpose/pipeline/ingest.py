"""Stage 1: Ingest — PDF ingestion and book registration."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from transpose.models.enums import SourceLanguage


@dataclass
class IngestInput:
    source_path: str
    title: str
    author: str | None = None
    source_language: SourceLanguage = SourceLanguage.HINDI


@dataclass
class IngestOutput:
    book_id: UUID
    source_hash: str
    source_blob_uri: str
    page_count: int
    already_existed: bool


async def run(input: IngestInput, ctx) -> IngestOutput:  # type: ignore[no-untyped-def]
    """Ingest a PDF: compute hash, dedup, store in blob, create book record."""
    import hashlib
    import logging
    from datetime import UTC, datetime
    from pathlib import Path

    import fitz  # PyMuPDF

    from transpose.models.book import Book
    from transpose.models.enums import BookStatus

    logger = logging.getLogger(__name__)

    # Read the source PDF
    source_path = Path(input.source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source PDF not found: {input.source_path}")

    with open(source_path, "rb") as f:
        pdf_data = f.read()

    # Compute SHA-256 hash for deduplication
    source_hash = hashlib.sha256(pdf_data).hexdigest()
    logger.info(f"Computed hash {source_hash} for {input.title}")

    # Check for existing book with same hash
    existing_book = await ctx.db.get_book_by_hash(source_hash)
    if existing_book:
        logger.info(f"Book already exists: {existing_book.id}")
        return IngestOutput(
            book_id=existing_book.id,
            source_hash=source_hash,
            source_blob_uri=existing_book.source_blob_uri,
            page_count=existing_book.page_count,
            already_existed=True,
        )

    # Count pages using PyMuPDF
    pdf_doc = fitz.open(stream=pdf_data, filetype="pdf")
    page_count = len(pdf_doc)
    pdf_doc.close()

    logger.info(f"PDF has {page_count} pages")

    # Upload to blob storage
    blob_name = f"{source_hash}.pdf"
    source_blob_uri = await ctx.blob.upload_pdf(
        container=ctx.settings.blob_container_source,
        blob_name=blob_name,
        data=pdf_data,
    )

    logger.info(f"Uploaded to blob storage: {source_blob_uri}")

    # Create book record
    book = Book(
        title=input.title,
        author=input.author,
        source_language=input.source_language,
        source_hash=source_hash,
        source_blob_uri=source_blob_uri,
        status=BookStatus.INGESTED,
        page_count=page_count,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    await ctx.db.create_book(book)
    logger.info(f"Created book record: {book.id}")

    return IngestOutput(
        book_id=book.id,
        source_hash=source_hash,
        source_blob_uri=source_blob_uri,
        page_count=page_count,
        already_existed=False,
    )

