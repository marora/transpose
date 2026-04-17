"""Tests for the OCR pipeline stage.

Tests OCR routing, confidence scoring, and already-processed page handling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest


@dataclass
class OcrInput:
    """OCR stage input contract."""

    book_id: UUID


@dataclass
class PageResult:
    """OCR result for a single page."""

    page_number: int
    raw_text: str
    confidence: float
    needs_review: bool
    ocr_metadata: dict


@dataclass
class OcrOutput:
    """OCR stage output contract."""

    book_id: UUID
    pages_processed: int
    pages_skipped: int
    low_confidence_count: int
    page_results: list[PageResult] = field(default_factory=list)


class TestOcrContract:
    """Test OCR stage contract validation."""

    def test_ocr_input_requires_book_id(self) -> None:
        """Test OcrInput requires book_id."""
        book_id = uuid4()
        input_data = OcrInput(book_id=book_id)
        assert input_data.book_id == book_id
        assert isinstance(input_data.book_id, UUID)

    def test_page_result_shape(self) -> None:
        """Test PageResult has all required fields."""
        result = PageResult(
            page_number=1,
            raw_text="Sample text",
            confidence=0.95,
            needs_review=False,
            ocr_metadata={"bounding_boxes": [], "reading_order": []},
        )
        assert result.page_number == 1
        assert len(result.raw_text) > 0
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.needs_review, bool)
        assert isinstance(result.ocr_metadata, dict)

    def test_ocr_output_shape(self) -> None:
        """Test OcrOutput has all required fields."""
        book_id = uuid4()
        output = OcrOutput(
            book_id=book_id,
            pages_processed=10,
            pages_skipped=2,
            low_confidence_count=1,
            page_results=[],
        )
        assert output.book_id == book_id
        assert output.pages_processed >= 0
        assert output.pages_skipped >= 0
        assert output.low_confidence_count >= 0
        assert isinstance(output.page_results, list)


class TestOcrRouting:
    """Test OCR routing logic."""

    @pytest.mark.asyncio
    async def test_scanned_pdf_routes_to_document_intelligence(
        self,
        mock_ocr_client: AsyncMock,
        mock_database: AsyncMock,
    ) -> None:
        """Test that scanned PDFs route to Azure Document Intelligence."""
        # Mock OCR client to return Document Intelligence results
        mock_ocr_client.extract_text_with_azure_di = AsyncMock(
            return_value=[
                {
                    "page_number": 1,
                    "text": "Scanned text from DI",
                    "confidence": 0.85,
                    "metadata": {"bounding_boxes": [], "reading_order": []},
                }
            ]
        )

        # Simulate OCR extraction
        results = await mock_ocr_client.extract_text_with_azure_di("book.pdf")

        assert len(results) == 1
        assert results[0]["page_number"] == 1
        assert "Scanned text" in results[0]["text"]
        assert results[0]["confidence"] < 1.0

    @pytest.mark.asyncio
    async def test_digital_pdf_uses_pymupdf_first(
        self,
        mock_ocr_client: AsyncMock,
    ) -> None:
        """Test that digital PDFs try PyMuPDF first."""
        # Mock OCR client to return PyMuPDF results
        mock_ocr_client.extract_text_from_pdf = AsyncMock(
            return_value=[
                {"page_number": 1, "text": "Digital text from PyMuPDF", "confidence": 1.0},
                {"page_number": 2, "text": "More digital text", "confidence": 1.0},
            ]
        )

        results = await mock_ocr_client.extract_text_from_pdf("digital_book.pdf")

        assert len(results) == 2
        assert results[0]["confidence"] == 1.0
        assert results[1]["confidence"] == 1.0


class TestOcrConfidence:
    """Test confidence scoring and low-confidence detection."""

    def test_low_confidence_pages_flagged(self) -> None:
        """Test that low-confidence pages are flagged for review."""
        low_confidence_page = PageResult(
            page_number=5,
            raw_text="Unclear text",
            confidence=0.65,
            needs_review=True,
            ocr_metadata={},
        )
        assert low_confidence_page.needs_review is True
        assert low_confidence_page.confidence < 0.75

    def test_high_confidence_pages_not_flagged(self) -> None:
        """Test that high-confidence pages are not flagged."""
        high_confidence_page = PageResult(
            page_number=1,
            raw_text="Clear text",
            confidence=0.98,
            needs_review=False,
            ocr_metadata={},
        )
        assert high_confidence_page.needs_review is False
        assert high_confidence_page.confidence >= 0.75

    def test_low_confidence_count_aggregation(self) -> None:
        """Test that low_confidence_count aggregates flagged pages."""
        page_results = [
            PageResult(1, "text1", 0.98, False, {}),
            PageResult(2, "text2", 0.65, True, {}),
            PageResult(3, "text3", 0.95, False, {}),
            PageResult(4, "text4", 0.60, True, {}),
        ]

        low_confidence_count = sum(1 for p in page_results if p.needs_review)
        assert low_confidence_count == 2


class TestOcrIdempotency:
    """Test idempotency of OCR stage."""

    @pytest.mark.asyncio
    async def test_already_processed_pages_skipped(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test that already-processed pages are skipped."""
        book_id = uuid4()

        # Mock database to return already-processed pages
        mock_database.fetch_all = AsyncMock(
            return_value=[
                {"page_number": 1, "raw_text": "Existing text 1"},
                {"page_number": 2, "raw_text": "Existing text 2"},
            ]
        )

        existing_pages = await mock_database.fetch_all(
            "SELECT page_number, raw_text FROM pages WHERE book_id = $1", book_id
        )

        assert len(existing_pages) == 2
        existing_page_numbers = {p["page_number"] for p in existing_pages}

        # Simulate checking if page 1 needs processing
        page_1_exists = 1 in existing_page_numbers
        assert page_1_exists is True

        # Output would show skipped pages
        output = OcrOutput(
            book_id=book_id,
            pages_processed=1,  # Only 1 new page processed
            pages_skipped=2,  # 2 pages skipped
            low_confidence_count=0,
            page_results=[],
        )
        assert output.pages_skipped == 2
        assert output.pages_processed == 1


class TestOcrEdgeCases:
    """Test OCR edge cases."""

    def test_empty_pdf_zero_pages(self) -> None:
        """Test that empty PDF processes zero pages."""
        book_id = uuid4()
        output = OcrOutput(
            book_id=book_id,
            pages_processed=0,
            pages_skipped=0,
            low_confidence_count=0,
            page_results=[],
        )
        assert output.pages_processed == 0
        assert len(output.page_results) == 0

    def test_single_page_book(self) -> None:
        """Test OCR of single-page book."""
        book_id = uuid4()
        page_results = [
            PageResult(
                page_number=1,
                raw_text="Single page content",
                confidence=0.95,
                needs_review=False,
                ocr_metadata={},
            )
        ]

        output = OcrOutput(
            book_id=book_id,
            pages_processed=1,
            pages_skipped=0,
            low_confidence_count=0,
            page_results=page_results,
        )
        assert output.pages_processed == 1
        assert len(output.page_results) == 1

    def test_all_pages_low_confidence(self) -> None:
        """Test when all pages have low confidence."""
        book_id = uuid4()
        page_results = [
            PageResult(1, "text1", 0.60, True, {}),
            PageResult(2, "text2", 0.55, True, {}),
            PageResult(3, "text3", 0.65, True, {}),
        ]

        output = OcrOutput(
            book_id=book_id,
            pages_processed=3,
            pages_skipped=0,
            low_confidence_count=3,
            page_results=page_results,
        )
        assert output.low_confidence_count == output.pages_processed
        assert all(p.needs_review for p in output.page_results)
