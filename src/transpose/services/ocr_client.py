"""Azure AI Document Intelligence client wrapper."""

from __future__ import annotations

import logging
import unicodedata
from uuid import UUID

from transpose.models.book import Page

logger = logging.getLogger(__name__)

_DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.5
_DEFAULT_OCR_CONCURRENCY = 5


class OcrClient:
    """Wraps Azure AI Document Intelligence for text extraction.

    All Azure SDK interactions are isolated here. Pipeline stages
    call this interface — never the SDK directly.
    """

    def __init__(
        self,
        endpoint: str,
        low_confidence_threshold: float = _DEFAULT_LOW_CONFIDENCE_THRESHOLD,
        ocr_concurrency: int = _DEFAULT_OCR_CONCURRENCY,
    ) -> None:
        self._endpoint = endpoint
        self._low_confidence_threshold = low_confidence_threshold
        self._ocr_concurrency = ocr_concurrency
        # Initialized lazily on first use
        self._client = None

    async def _get_client(self):
        """Lazy-initialize the Document Intelligence client with Managed Identity."""
        if self._client is None:
            from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            self._client = DocumentIntelligenceClient(
                endpoint=self._endpoint, credential=credential
            )
        return self._client

    async def extract_pages(
        self, blob_uri: str, book_id: UUID, *, locale: str = "hi"
    ) -> list[Page]:
        """Extract text from all pages of a PDF using the prebuilt-read model.

        Args:
            blob_uri: Azure Blob Storage URI of the source PDF.
            book_id: ID of the book being processed.
            locale: BCP-47 locale hint for OCR (default: 'hi' for Hindi/Devanagari).

        Returns:
            List of Page objects with extracted text and confidence scores.
        """
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        client = await self._get_client()

        logger.info("Starting Document Intelligence analysis with locale=%s", locale)

        # Start the analysis job with prebuilt-read model and locale hint
        poller = await client.begin_analyze_document(
            model_id="prebuilt-read",
            analyze_request=AnalyzeDocumentRequest(url_source=blob_uri),
            locale=locale,
        )

        # Wait for completion
        result = await poller.result()

        # Parse pages from the result
        pages: list[Page] = []

        if result.pages:
            for page_num, page in enumerate(result.pages, start=1):
                # Extract text from the page
                # The prebuilt-read model gives us lines
                page_text = ""
                page_confidence_sum = 0.0
                word_count_for_avg = 0

                if page.lines:
                    for line in page.lines:
                        page_text += line.content + "\n"
                        # Aggregate confidence from words if available
                        if page.words:
                            for word in page.words:
                                if (
                                    word.span.offset >= line.span.offset
                                    and word.span.offset
                                    < (line.span.offset + line.span.length)
                                    and word.confidence is not None
                                ):
                                    page_confidence_sum += word.confidence
                                    word_count_for_avg += 1

                # Word-level confidence logging for debugging garbled output
                if page.words:
                    low_words = [
                        w for w in page.words
                        if w.confidence is not None and w.confidence < 0.5
                    ]
                    if low_words:
                        sample = low_words[:5]
                        logger.warning(
                            "Page %d: %d/%d words below 0.5 confidence. "
                            "Sample: %s",
                            page_num,
                            len(low_words),
                            len(page.words),
                            [(w.content, round(w.confidence, 3)) for w in sample],
                        )

                # Calculate average confidence
                avg_confidence = (
                    page_confidence_sum / word_count_for_avg
                    if word_count_for_avg > 0
                    else 1.0
                )

                # Apply Unicode NFC normalization to fix garbled Devanagari
                page_text = unicodedata.normalize("NFC", page_text.strip())

                # Build OCR metadata
                ocr_metadata = {
                    "page_width": page.width if hasattr(page, "width") else 0,
                    "page_height": page.height if hasattr(page, "height") else 0,
                    "unit": page.unit if hasattr(page, "unit") else "pixel",
                    "line_count": len(page.lines) if page.lines else 0,
                    "word_count": len(page.words) if page.words else 0,
                    "locale_hint": locale,
                }

                needs_review = avg_confidence < self._low_confidence_threshold
                if needs_review:
                    logger.warning(
                        "Page %d flagged for review: avg_confidence=%.3f (threshold=%.2f)",
                        page_num,
                        avg_confidence,
                        self._low_confidence_threshold,
                    )
                    ocr_metadata["review_reason"] = (
                        f"confidence {avg_confidence:.3f} below threshold "
                        f"{self._low_confidence_threshold}"
                    )

                pages.append(
                    Page(
                        book_id=book_id,
                        page_number=page_num,
                        raw_text=page_text,
                        confidence=avg_confidence,
                        needs_review=needs_review,
                        ocr_metadata=ocr_metadata,
                    )
                )

        return pages

    async def close(self) -> None:
        """Release SDK resources."""
        if self._client is not None:
            await self._client.close()
