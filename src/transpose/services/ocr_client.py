"""Azure AI Document Intelligence client wrapper."""

from __future__ import annotations

import asyncio
import logging
import unicodedata
from uuid import UUID

from transpose.models.book import Page

logger = logging.getLogger(__name__)

_DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.5
_DEFAULT_OCR_CONCURRENCY = 5
_DEFAULT_OCR_BATCH_SIZE = 10


def _compute_page_ranges(total_pages: int, batch_size: int) -> list[tuple[int, int]]:
    """Split a 1-indexed page count into contiguous (start, end) ranges.

    Inclusive on both ends; (1, N) is the single-batch fallback.
    Used to fan out Document Intelligence ``begin_analyze_document`` calls
    across multiple page-range jobs so OCR scales with ``ocr_concurrency``.
    """
    if total_pages <= 0:
        return []
    if batch_size <= 0:
        batch_size = total_pages
    ranges: list[tuple[int, int]] = []
    start = 1
    while start <= total_pages:
        end = min(start + batch_size - 1, total_pages)
        ranges.append((start, end))
        start = end + 1
    return ranges


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
        ocr_batch_size: int = _DEFAULT_OCR_BATCH_SIZE,
    ) -> None:
        self._endpoint = endpoint
        self._low_confidence_threshold = low_confidence_threshold
        self._ocr_concurrency = max(1, ocr_concurrency)
        self._ocr_batch_size = max(1, ocr_batch_size)
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

    async def _analyze_range(
        self,
        client,
        blob_uri: str,
        *,
        locale: str,
        pages_arg: str | None,
        semaphore: asyncio.Semaphore,
    ):
        """Submit one ``begin_analyze_document`` job and await its result.

        Honors the shared semaphore so the in-flight job count never exceeds
        ``ocr_concurrency``.
        """
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        async with semaphore:
            kwargs: dict = {
                "model_id": "prebuilt-read",
                "analyze_request": AnalyzeDocumentRequest(url_source=blob_uri),
                "locale": locale,
            }
            if pages_arg:
                kwargs["pages"] = pages_arg
            poller = await client.begin_analyze_document(**kwargs)
            return await poller.result()

    def _result_to_pages(
        self,
        result,
        book_id: UUID,
        *,
        locale: str,
        page_number_offset: int = 0,
    ) -> list[Page]:
        """Convert a Document Intelligence result into ``Page`` rows.

        ``page_number_offset`` is added to the 1-based index Document
        Intelligence reports for the batch so merged output preserves
        the canonical page order of the source PDF.
        """
        pages: list[Page] = []
        if not result.pages:
            return pages

        for batch_index, page in enumerate(result.pages, start=1):
            page_num = page_number_offset + batch_index
            page_text = ""
            page_confidence_sum = 0.0
            word_count_for_avg = 0

            if page.lines:
                for line in page.lines:
                    page_text += line.content + "\n"
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

            if page.words:
                low_words = [
                    w for w in page.words
                    if w.confidence is not None and w.confidence < 0.5
                ]
                if low_words:
                    sample = low_words[:5]
                    logger.warning(
                        "Page %d: %d/%d words below 0.5 confidence. Sample: %s",
                        page_num,
                        len(low_words),
                        len(page.words),
                        [(w.content, round(w.confidence, 3)) for w in sample],
                    )

            avg_confidence = (
                page_confidence_sum / word_count_for_avg
                if word_count_for_avg > 0
                else 1.0
            )

            page_text = unicodedata.normalize("NFC", page_text.strip())

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

    async def extract_pages(
        self,
        blob_uri: str,
        book_id: UUID,
        *,
        locale: str = "hi",
        total_pages: int | None = None,
    ) -> list[Page]:
        """Extract text from all pages of a PDF using the prebuilt-read model.

        When ``total_pages`` is provided and exceeds the configured batch
        size, the PDF is split into contiguous page ranges and submitted as
        concurrent ``begin_analyze_document`` jobs (gated by
        ``ocr_concurrency``). Results are merged back into canonical order.
        When ``total_pages`` is unknown or fits in one batch, a single
        analyze job runs and returns the whole document.
        """
        client = await self._get_client()

        if total_pages is None or total_pages <= self._ocr_batch_size:
            logger.info(
                "Starting Document Intelligence analysis with locale=%s (single batch)",
                locale,
            )
            semaphore = asyncio.Semaphore(1)
            result = await self._analyze_range(
                client,
                blob_uri,
                locale=locale,
                pages_arg=None,
                semaphore=semaphore,
            )
            return self._result_to_pages(
                result, book_id, locale=locale, page_number_offset=0
            )

        ranges = _compute_page_ranges(total_pages, self._ocr_batch_size)
        logger.info(
            "Starting batched Document Intelligence analysis: %d pages, "
            "%d batches of up to %d, ocr_concurrency=%d, locale=%s",
            total_pages,
            len(ranges),
            self._ocr_batch_size,
            self._ocr_concurrency,
            locale,
        )

        semaphore = asyncio.Semaphore(self._ocr_concurrency)
        tasks = [
            self._analyze_range(
                client,
                blob_uri,
                locale=locale,
                pages_arg=f"{start}-{end}",
                semaphore=semaphore,
            )
            for (start, end) in ranges
        ]
        results = await asyncio.gather(*tasks)

        merged: list[Page] = []
        for (start, _end), result in zip(ranges, results, strict=True):
            merged.extend(
                self._result_to_pages(
                    result,
                    book_id,
                    locale=locale,
                    page_number_offset=start - 1,
                )
            )
        merged.sort(key=lambda p: p.page_number)
        return merged

    async def close(self) -> None:
        """Release SDK resources."""
        if self._client is not None:
            await self._client.close()
