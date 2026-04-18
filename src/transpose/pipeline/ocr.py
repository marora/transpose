"""Stage 2: OCR — Text extraction via Azure AI Document Intelligence."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from uuid import UUID

from transpose.models.book import Page

logger = logging.getLogger(__name__)

# Devanagari Unicode block: U+0900–U+097F
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
# Unicode replacement character — indicates decode failures
_REPLACEMENT_CHAR = "\ufffd"
# Minimum characters expected per page (catch blank/failed extractions)
_MIN_PAGE_TEXT_LENGTH = 10
# Maximum ratio of replacement chars to total text before flagging
_MAX_REPLACEMENT_RATIO = 0.05


def _normalize_text(text: str) -> str:
    """Apply Unicode NFC normalization to extracted text."""
    return unicodedata.normalize("NFC", text)


def _validate_page(
    page: Page,
    source_language: str,
) -> tuple[bool, list[str]]:
    """Validate OCR output quality for a single page.

    Returns:
        (is_valid, list_of_issues) — is_valid is False when the page
        should be flagged for review.
    """
    issues: list[str] = []
    text = page.raw_text

    # Check minimum text length
    if len(text.strip()) < _MIN_PAGE_TEXT_LENGTH:
        issues.append(
            f"text too short ({len(text.strip())} chars, "
            f"minimum {_MIN_PAGE_TEXT_LENGTH})"
        )

    # Check for Devanagari codepoints when source is Hindi
    if source_language in ("hindi", "hi") and text.strip():
        devanagari_count = len(_DEVANAGARI_RE.findall(text))
        if devanagari_count == 0:
            issues.append("no Devanagari codepoints (U+0900-U+097F) found")

    # Check for excessive replacement characters
    replacement_count = text.count(_REPLACEMENT_CHAR)
    if replacement_count > 0:
        ratio = replacement_count / max(len(text), 1)
        if ratio > _MAX_REPLACEMENT_RATIO:
            issues.append(
                f"excessive replacement chars: {replacement_count} "
                f"({ratio:.1%} of text)"
            )

    return (len(issues) == 0, issues)


@dataclass
class OcrInput:
    book_id: UUID


@dataclass
class OcrOutput:
    book_id: UUID
    pages_processed: int
    pages_skipped: int
    low_confidence_count: int
    page_results: list[Page] = field(default_factory=list)


async def run(input: OcrInput, ctx) -> OcrOutput:  # type: ignore[no-untyped-def]
    """Extract text from all pages of a book's PDF.

    Uses Document Intelligence for scanned PDFs,
    PyMuPDF for digital PDFs with text layers.
    Skips pages already processed (idempotent).
    """
    import fitz  # PyMuPDF

    from transpose.models.book import Page
    from transpose.models.enums import BookStatus
    from transpose.observability.metrics import low_confidence_pages, pages_processed

    # Get book from database
    book = await ctx.db.get_book(input.book_id)
    if not book:
        raise ValueError(f"Book not found: {input.book_id}")

    logger.info("Starting OCR for book: %s (%s)", book.title, book.id)

    # Get existing page numbers (idempotent)
    existing_pages = await ctx.db.get_existing_page_numbers(input.book_id)
    logger.info("Found %d existing pages", len(existing_pages))

    # Try digital text extraction first with PyMuPDF
    logger.info("Attempting digital text extraction...")

    # Download the PDF
    blob_name = book.source_blob_uri.split("/")[-1]
    pdf_data = await ctx.blob.download_blob(
        container=ctx.settings.blob_container_source,
        blob_name=blob_name,
    )

    # Open PDF with PyMuPDF
    pdf_doc = fitz.open(stream=pdf_data, filetype="pdf")
    page_results: list[Page] = []
    low_confidence_count = 0

    # Check if PDF has text layers (digital PDF)
    has_text_layer = False
    for page_num in range(1, min(4, len(pdf_doc) + 1)):  # Check first 3 pages
        page = pdf_doc[page_num - 1]
        text = page.get_text()
        if text and len(text.strip()) > 100:
            has_text_layer = True
            break

    source_lang = str(book.source_language) if hasattr(book, "source_language") else ""

    if has_text_layer:
        logger.info("PDF has text layers, using digital extraction")
        # Extract text from all pages using PyMuPDF
        for page_num in range(1, len(pdf_doc) + 1):
            if page_num in existing_pages:
                continue

            page = pdf_doc[page_num - 1]
            text = page.get_text()

            # Apply NFC normalization to digital text too
            text = _normalize_text(text.strip())

            page_obj = Page(
                book_id=input.book_id,
                page_number=page_num,
                raw_text=text,
                confidence=1.0,  # Digital text has high confidence
                needs_review=False,
                ocr_metadata={"source": "digital_extraction"},
            )

            # Validate even digital extraction
            is_valid, issues = _validate_page(page_obj, source_lang)
            if not is_valid:
                page_obj.needs_review = True
                page_obj.ocr_metadata["validation_issues"] = issues
                low_confidence_count += 1
                logger.warning(
                    "Page %d (digital) failed validation: %s",
                    page_num,
                    "; ".join(issues),
                )
            else:
                logger.debug("Page %d (digital) passed validation", page_num)

            page_results.append(page_obj)

        pdf_doc.close()
    else:
        logger.info("PDF is scanned, using Document Intelligence OCR")
        pdf_doc.close()

        # Use Document Intelligence for scanned PDFs
        ocr_pages = await ctx.ocr.extract_pages(book.source_blob_uri, input.book_id)

        # Filter out already-processed pages and validate each
        for page in ocr_pages:
            if page.page_number in existing_pages:
                continue

            # Post-OCR validation
            is_valid, issues = _validate_page(page, source_lang)
            if not is_valid:
                page.needs_review = True
                page.ocr_metadata["validation_issues"] = issues
                logger.warning(
                    "Page %d (OCR) failed validation: %s",
                    page.page_number,
                    "; ".join(issues),
                )

            if page.needs_review:
                low_confidence_count += 1

            page_results.append(page)

    # Log validation summary
    valid_count = sum(1 for p in page_results if not p.needs_review)
    logger.info(
        "OCR complete: %d pages extracted, %d valid, %d need review",
        len(page_results),
        valid_count,
        low_confidence_count,
    )

    # Save pages to database
    if page_results:
        await ctx.db.create_pages(page_results)
        logger.info("Saved %d pages to database", len(page_results))

        # Record metrics
        pages_processed.add(len(page_results), {"book_id": str(input.book_id)})
        if low_confidence_count > 0:
            low_confidence_pages.add(low_confidence_count, {"book_id": str(input.book_id)})

    # Update book status
    await ctx.db.update_book_status(input.book_id, BookStatus.OCR_COMPLETE)

    # Update progress in state
    await ctx.state.set_progress(
        str(input.book_id),
        "ocr",
        len(existing_pages) + len(page_results),
        book.page_count,
    )

    return OcrOutput(
        book_id=input.book_id,
        pages_processed=len(page_results),
        pages_skipped=len(existing_pages),
        low_confidence_count=low_confidence_count,
        page_results=page_results,
    )

