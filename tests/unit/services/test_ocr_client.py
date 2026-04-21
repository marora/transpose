"""Tests for transpose.services.ocr_client — Azure Document Intelligence wrapper.

All Azure SDK calls are mocked. Tests verify:
- Lazy client initialization
- Page extraction with confidence scoring
- NFC normalization of extracted text
- Low-confidence flagging
- Empty pages and no-word scenarios
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from transpose.services.ocr_client import _DEFAULT_LOW_CONFIDENCE_THRESHOLD, OcrClient


@pytest.fixture
def ocr_client() -> OcrClient:
    return OcrClient(endpoint="https://test.cognitiveservices.azure.com")


def _make_word(content: str, offset: int, length: int, confidence: float):
    """Create a fake word object."""
    return SimpleNamespace(
        content=content,
        span=SimpleNamespace(offset=offset, length=length),
        confidence=confidence,
    )


def _make_line(content: str, offset: int):
    """Create a fake line object."""
    return SimpleNamespace(
        content=content,
        span=SimpleNamespace(offset=offset, length=len(content)),
    )


def _make_page(lines, words, *, width=612, height=792):
    """Create a fake page object."""
    return SimpleNamespace(
        lines=lines,
        words=words,
        width=width,
        height=height,
        unit="pixel",
    )


# ---------------------------------------------------------------------------
# Lazy initialization
# ---------------------------------------------------------------------------


class TestOcrClientInit:
    def test_client_starts_none(self, ocr_client: OcrClient) -> None:
        assert ocr_client._client is None

    @pytest.mark.asyncio
    async def test_lazy_init_creates_client(self, ocr_client: OcrClient) -> None:
        with (
            patch("azure.identity.aio.DefaultAzureCredential"),
            patch("azure.ai.documentintelligence.aio.DocumentIntelligenceClient") as mock_di,
        ):
            mock_di.return_value = AsyncMock()
            client = await ocr_client._get_client()
            assert client is not None


# ---------------------------------------------------------------------------
# extract_pages — happy path
# ---------------------------------------------------------------------------


class TestExtractPages:
    @pytest.mark.asyncio
    async def test_single_page_extraction(self, ocr_client: OcrClient) -> None:
        """Single page with one line, high confidence."""
        book_id = uuid4()
        word = _make_word("धर्म", offset=0, length=4, confidence=0.95)
        line = _make_line("धर्म", offset=0)
        page = _make_page([line], [word])

        mock_result = SimpleNamespace(pages=[page])
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        pages = await ocr_client.extract_pages(
            "https://storage/container/book.pdf", book_id
        )

        assert len(pages) == 1
        assert pages[0].page_number == 1
        assert pages[0].book_id == book_id
        assert "धर्म" in pages[0].raw_text
        assert pages[0].confidence == pytest.approx(0.95)
        assert pages[0].needs_review is False

    @pytest.mark.asyncio
    async def test_multi_page_extraction(self, ocr_client: OcrClient) -> None:
        """Multiple pages are returned in order."""
        book_id = uuid4()
        pages_data = []
        for i in range(3):
            word = _make_word(f"word{i}", offset=0, length=5, confidence=0.9)
            line = _make_line(f"word{i}", offset=0)
            pages_data.append(_make_page([line], [word]))

        mock_result = SimpleNamespace(pages=pages_data)
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        pages = await ocr_client.extract_pages("https://storage/book.pdf", book_id)
        assert len(pages) == 3
        assert [p.page_number for p in pages] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_nfc_normalization_applied(self, ocr_client: OcrClient) -> None:
        """Extracted text is NFC-normalized."""
        import unicodedata

        book_id = uuid4()
        # Use NFD decomposed text — should be recomposed
        nfd_text = unicodedata.normalize("NFD", "कर्म")
        word = _make_word(nfd_text, offset=0, length=len(nfd_text), confidence=0.9)
        line = _make_line(nfd_text, offset=0)
        page = _make_page([line], [word])

        mock_result = SimpleNamespace(pages=[page])
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        pages = await ocr_client.extract_pages("https://storage/book.pdf", book_id)
        assert unicodedata.is_normalized("NFC", pages[0].raw_text)


# ---------------------------------------------------------------------------
# Low-confidence flagging
# ---------------------------------------------------------------------------


class TestLowConfidenceFlagging:
    @pytest.mark.asyncio
    async def test_low_confidence_flagged(self, ocr_client: OcrClient) -> None:
        """Page with avg confidence below threshold → needs_review=True."""
        book_id = uuid4()
        word = _make_word("garbled", offset=0, length=7, confidence=0.3)
        line = _make_line("garbled", offset=0)
        page = _make_page([line], [word])

        mock_result = SimpleNamespace(pages=[page])
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        pages = await ocr_client.extract_pages("https://storage/book.pdf", book_id)
        assert pages[0].needs_review is True
        assert pages[0].confidence < _DEFAULT_LOW_CONFIDENCE_THRESHOLD

    @pytest.mark.asyncio
    async def test_high_confidence_not_flagged(self, ocr_client: OcrClient) -> None:
        book_id = uuid4()
        word = _make_word("clear", offset=0, length=5, confidence=0.98)
        line = _make_line("clear", offset=0)
        page = _make_page([line], [word])

        mock_result = SimpleNamespace(pages=[page])
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        pages = await ocr_client.extract_pages("https://storage/book.pdf", book_id)
        assert pages[0].needs_review is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestOcrEdgeCases:
    @pytest.mark.asyncio
    async def test_empty_result(self, ocr_client: OcrClient) -> None:
        """No pages in result → empty list."""
        mock_result = SimpleNamespace(pages=None)
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        pages = await ocr_client.extract_pages("https://storage/book.pdf", uuid4())
        assert pages == []

    @pytest.mark.asyncio
    async def test_page_with_no_lines(self, ocr_client: OcrClient) -> None:
        """Page with no lines → empty text, default confidence."""
        book_id = uuid4()
        page = _make_page(None, None)

        mock_result = SimpleNamespace(pages=[page])
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        pages = await ocr_client.extract_pages("https://storage/book.pdf", book_id)
        assert len(pages) == 1
        assert pages[0].raw_text == ""
        assert pages[0].confidence == 1.0  # default when no words

    @pytest.mark.asyncio
    async def test_locale_passed_to_sdk(self, ocr_client: OcrClient) -> None:
        """Locale hint is forwarded to the SDK call."""
        mock_result = SimpleNamespace(pages=[])
        mock_poller = AsyncMock()
        mock_poller.result = AsyncMock(return_value=mock_result)

        mock_client = AsyncMock()
        mock_client.begin_analyze_document = AsyncMock(return_value=mock_poller)
        ocr_client._client = mock_client

        await ocr_client.extract_pages(
            "https://storage/book.pdf", uuid4(), locale="pa"
        )

        call_kwargs = mock_client.begin_analyze_document.call_args
        assert call_kwargs[1]["locale"] == "pa"


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestOcrClientClose:
    @pytest.mark.asyncio
    async def test_close_when_initialized(self, ocr_client: OcrClient) -> None:
        mock_client = AsyncMock()
        ocr_client._client = mock_client
        await ocr_client.close()
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self, ocr_client: OcrClient) -> None:
        await ocr_client.close()  # should not raise
