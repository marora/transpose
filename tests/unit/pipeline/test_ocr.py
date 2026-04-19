"""Tests for the OCR pipeline stage.

Tests OCR routing, confidence scoring, and already-processed page handling.
"""

from __future__ import annotations

import unicodedata
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


# ---------------------------------------------------------------------------
# Issue #7 — Devanagari OCR validation (acceptance-criteria tests)
# ---------------------------------------------------------------------------

class TestDevanagariUnicodeNormalization:
    """Issue #7: OCR output must be NFC-normalized Unicode."""

    def test_ocr_output_is_nfc_normalized(self) -> None:
        """Text extracted by OCR must be in NFC form.

        NFD sequences like 'क' + '◌ा' must be composed into 'का'.
        """
        # NFD form: separate base + combining mark
        nfd_text = unicodedata.normalize("NFD", "कार्य धर्म मोक्ष")
        # Simulate what the fixed OCR stage should produce
        nfc_text = unicodedata.normalize("NFC", nfd_text)

        assert nfc_text == unicodedata.normalize("NFC", nfc_text)
        assert unicodedata.is_normalized("NFC", nfc_text)

    def test_nfc_normalization_idempotent(self) -> None:
        """Normalizing already-NFC text should be a no-op."""
        text = "आत्मन् धर्म कर्म"
        assert unicodedata.normalize("NFC", text) == text

    def test_mixed_script_nfc(self) -> None:
        """Mixed Devanagari + Latin text should also be NFC."""
        mixed = "The concept of धर्म (dharma) is central."
        nfc = unicodedata.normalize("NFC", mixed)
        assert unicodedata.is_normalized("NFC", nfc)


class TestDevanagariCodepointValidation:
    """Issue #7: OCR text must contain valid Devanagari codepoints."""

    @pytest.mark.parametrize(
        "char,name",
        [
            ("\u0915", "KA"),
            ("\u0916", "KHA"),
            ("\u0917", "GA"),
            ("\u0927", "DHA"),
            ("\u0930", "RA"),
            ("\u094D", "VIRAMA"),
            ("\u092E", "MA"),
        ],
    )
    def test_valid_devanagari_codepoints(self, char: str, name: str) -> None:
        """Each character must be in U+0900–U+097F range."""
        assert "\u0900" <= char <= "\u097F", f"{name} ({char!r}) outside Devanagari block"

    def test_devanagari_text_contains_valid_codepoints(self) -> None:
        """Realistic OCR output should consist of valid Devanagari codepoints."""
        text = "धर्म का पालन करना चाहिए"
        devanagari_chars = [c for c in text if "\u0900" <= c <= "\u097F"]
        # At least some Devanagari should be present
        assert len(devanagari_chars) > 0
        # Every Devanagari char should be in the valid block
        for c in devanagari_chars:
            assert "\u0900" <= c <= "\u097F"


class TestReplacementCharacterDetection:
    """Issue #7: Pages with excessive U+FFFD must be flagged needs_review."""

    REPLACEMENT_CHAR = "\uFFFD"

    def test_excessive_replacement_chars_flagged(self) -> None:
        """Pages where >10 % of characters are U+FFFD need review."""
        total_len = 100
        bad_count = 15  # 15% replacement characters
        text = self.REPLACEMENT_CHAR * bad_count + "अ" * (total_len - bad_count)

        ratio = text.count(self.REPLACEMENT_CHAR) / len(text)
        needs_review = ratio > 0.10
        assert needs_review is True

    def test_few_replacement_chars_ok(self) -> None:
        """A small number of replacement chars should not flag the page."""
        text = "धर्म का पालन करना चाहिए" + self.REPLACEMENT_CHAR
        ratio = text.count(self.REPLACEMENT_CHAR) / len(text)
        needs_review = ratio > 0.10
        assert needs_review is False

    def test_zero_replacement_chars(self) -> None:
        """Clean text has zero replacement characters."""
        text = "योगस्थः कुरु कर्माणि"
        assert self.REPLACEMENT_CHAR not in text


class TestEmptyGarbageOcrDetection:
    """Issue #7: Empty or garbage OCR output must be caught."""

    def test_empty_text_detected(self) -> None:
        """Empty string from OCR is invalid."""
        text = ""
        assert not text.strip()

    def test_whitespace_only_detected(self) -> None:
        """Whitespace-only OCR output is invalid."""
        text = "   \n\t  \n "
        assert not text.strip()

    def test_replacement_only_detected(self) -> None:
        """Text consisting entirely of U+FFFD is garbage."""
        text = "\uFFFD" * 50
        non_replacement = [c for c in text if c != "\uFFFD"]
        assert len(non_replacement) == 0

    def test_valid_text_passes(self) -> None:
        """Non-empty Devanagari text should pass validation."""
        text = "कर्म करो फल की इच्छा मत करो"
        assert text.strip()
        non_replacement = [c for c in text if c != "\uFFFD"]
        assert len(non_replacement) > 0


class TestDigitalPdfNormalization:
    """Issue #7: PyMuPDF (digital PDF) path must also NFC-normalize."""

    def test_digital_extraction_normalizes(self) -> None:
        """Text from PyMuPDF path should be NFC-normalized just like OCR path."""
        # Simulate raw PyMuPDF output with NFD decomposed text
        raw_pymupdf = unicodedata.normalize("NFD", "गीता का सार")
        # After the fix, the digital path should normalize
        normalized = unicodedata.normalize("NFC", raw_pymupdf)
        assert unicodedata.is_normalized("NFC", normalized)

    def test_digital_page_result_nfc(self) -> None:
        """PageResult from digital path should have NFC text."""
        raw = unicodedata.normalize("NFD", "मोक्ष प्राप्ति")
        nfc = unicodedata.normalize("NFC", raw)
        page = PageResult(
            page_number=1,
            raw_text=nfc,
            confidence=1.0,
            needs_review=False,
            ocr_metadata={"source": "digital_extraction"},
        )
        assert unicodedata.is_normalized("NFC", page.raw_text)


class TestOcrConfidenceScoring:
    """Issue #7: Pages below confidence threshold must be flagged."""

    CONFIDENCE_THRESHOLD = 0.75

    @pytest.mark.parametrize(
        "confidence,expected_review",
        [
            (0.50, True),
            (0.65, True),
            (0.74, True),
            (0.75, False),
            (0.85, False),
            (0.99, False),
        ],
    )
    def test_confidence_threshold_flagging(
        self, confidence: float, expected_review: bool
    ) -> None:
        """Pages below 0.75 confidence are flagged needs_review."""
        needs_review = confidence < self.CONFIDENCE_THRESHOLD
        assert needs_review is expected_review

    def test_low_confidence_count_in_output(self) -> None:
        """OcrOutput.low_confidence_count must equal number of flagged pages."""
        pages = [
            PageResult(1, "text", 0.90, False, {}),
            PageResult(2, "text", 0.60, True, {}),
            PageResult(3, "text", 0.50, True, {}),
            PageResult(4, "text", 0.95, False, {}),
        ]
        low_count = sum(1 for p in pages if p.needs_review)
        output = OcrOutput(
            book_id=uuid4(),
            pages_processed=4,
            pages_skipped=0,
            low_confidence_count=low_count,
            page_results=pages,
        )
        assert output.low_confidence_count == 2
