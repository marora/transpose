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
    blob_uri: str | None = None


@dataclass
class IngestOutput:
    book_id: UUID
    source_hash: str
    source_blob_uri: str
    page_count: int
    already_existed: bool


def _parse_blob_uri(blob_uri: str) -> tuple[str, str]:
    """Extract (container, blob_name) from a full Azure Blob Storage URI.

    Example: https://transposedevst.blob.core.windows.net/source-pdfs/test.pdf
             → ("source-pdfs", "test.pdf")
    """
    from urllib.parse import urlparse

    parsed = urlparse(blob_uri)
    # Path is /container/blob_name
    parts = parsed.path.lstrip("/").split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Cannot parse blob URI: {blob_uri}")
    return parts[0], parts[1]


async def run(input: IngestInput, ctx) -> IngestOutput:  # type: ignore[no-untyped-def]
    """Ingest a PDF: compute hash, dedup, store in blob, create book record.

    Supports two modes:
    - Local file (source_path): reads from disk, uploads to blob storage.
    - Blob URI (blob_uri): downloads from blob storage, skips upload.
    """
    import hashlib
    import logging
    from datetime import UTC, datetime
    from pathlib import Path

    import fitz  # PyMuPDF

    from transpose.models.book import Book
    from transpose.models.enums import BookStatus

    logger = logging.getLogger(__name__)

    # --- Acquire PDF data ---
    if input.blob_uri:
        # Download from blob storage
        logger.info(f"Downloading PDF from blob: {input.blob_uri}")
        container, blob_name = _parse_blob_uri(input.blob_uri)
        pdf_data = await ctx.blob.download_blob(container=container, blob_name=blob_name)
        source_blob_uri = input.blob_uri
        skip_upload = True
    else:
        # Read from local file
        source_path = Path(input.source_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Source PDF not found: {input.source_path}")

        with open(source_path, "rb") as f:
            pdf_data = f.read()
        skip_upload = False
        source_blob_uri = ""  # will be set after upload

    # --- Compute hash for deduplication ---
    source_hash = hashlib.sha256(pdf_data).hexdigest()
    logger.info(f"Computed hash {source_hash} for {input.title}")

    # --- Check for existing book with same hash ---
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

    # --- Count pages ---
    pdf_doc = fitz.open(stream=pdf_data, filetype="pdf")
    page_count = len(pdf_doc)
    pdf_doc.close()
    logger.info(f"PDF has {page_count} pages")

    # --- Upload to blob storage (only for local files) ---
    if not skip_upload:
        blob_name = f"{source_hash}.pdf"
        source_blob_uri = await ctx.blob.upload_pdf(
            container=ctx.settings.blob_container_source,
            blob_name=blob_name,
            data=pdf_data,
        )
        logger.info(f"Uploaded to blob storage: {source_blob_uri}")

    # --- Create book record ---
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

