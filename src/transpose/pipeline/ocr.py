"""Stage 2: OCR — Text extraction via Azure AI Document Intelligence."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from transpose.models.book import Page


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
    import logging

    import fitz  # PyMuPDF

    from transpose.models.book import Page
    from transpose.models.enums import BookStatus
    from transpose.observability.metrics import low_confidence_pages, pages_processed

    logger = logging.getLogger(__name__)

    # Get book from database
    book = await ctx.db.get_book(input.book_id)
    if not book:
        raise ValueError(f"Book not found: {input.book_id}")

    logger.info(f"Starting OCR for book: {book.title} ({book.id})")

    # Get existing page numbers (idempotent)
    existing_pages = await ctx.db.get_existing_page_numbers(input.book_id)
    logger.info(f"Found {len(existing_pages)} existing pages")

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

    if has_text_layer:
        logger.info("PDF has text layers, using digital extraction")
        # Extract text from all pages using PyMuPDF
        for page_num in range(1, len(pdf_doc) + 1):
            if page_num in existing_pages:
                continue

            page = pdf_doc[page_num - 1]
            text = page.get_text()

            page_obj = Page(
                book_id=input.book_id,
                page_number=page_num,
                raw_text=text.strip(),
                confidence=1.0,  # Digital text has high confidence
                needs_review=False,
                ocr_metadata={"source": "digital_extraction"},
            )
            page_results.append(page_obj)

        pdf_doc.close()
    else:
        logger.info("PDF is scanned, using Document Intelligence OCR")
        pdf_doc.close()

        # Use Document Intelligence for scanned PDFs
        ocr_pages = await ctx.ocr.extract_pages(book.source_blob_uri, input.book_id)

        # Filter out already-processed pages
        for page in ocr_pages:
            if page.page_number in existing_pages:
                continue
            page_results.append(page)
            if page.needs_review:
                low_confidence_count += 1

    # Save pages to database
    if page_results:
        await ctx.db.create_pages(page_results)
        logger.info(f"Saved {len(page_results)} pages to database")

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

