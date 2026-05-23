"""Tests for batched OCR extraction (#96).

Verifies that ``OcrClient.extract_pages`` fans out ``begin_analyze_document``
calls across page ranges when ``total_pages`` exceeds the batch size,
respects ``ocr_concurrency``, and merges results back in canonical order
with correct page-number offsets.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from transpose.services.ocr_client import OcrClient, _compute_page_ranges


def _make_word(content: str, offset: int, length: int, confidence: float):
    return SimpleNamespace(
        content=content,
        span=SimpleNamespace(offset=offset, length=length),
        confidence=confidence,
    )


def _make_line(content: str, offset: int):
    return SimpleNamespace(
        content=content,
        span=SimpleNamespace(offset=offset, length=len(content)),
    )


def _make_page(idx: int):
    word = _make_word(f"w{idx}", offset=0, length=2, confidence=0.95)
    line = _make_line(f"w{idx}", offset=0)
    return SimpleNamespace(
        lines=[line], words=[word], width=612, height=792, unit="pixel",
    )


# ---------------------------------------------------------------------------
# _compute_page_ranges
# ---------------------------------------------------------------------------


class TestComputePageRanges:
    def test_empty(self) -> None:
        assert _compute_page_ranges(0, 10) == []
        assert _compute_page_ranges(-1, 10) == []

    def test_single_batch_fits_all(self) -> None:
        assert _compute_page_ranges(5, 10) == [(1, 5)]

    def test_exact_multiple(self) -> None:
        assert _compute_page_ranges(20, 10) == [(1, 10), (11, 20)]

    def test_remainder(self) -> None:
        assert _compute_page_ranges(25, 10) == [(1, 10), (11, 20), (21, 25)]

    def test_batch_size_one(self) -> None:
        assert _compute_page_ranges(3, 1) == [(1, 1), (2, 2), (3, 3)]

    def test_zero_batch_size_falls_back_to_single(self) -> None:
        assert _compute_page_ranges(5, 0) == [(1, 5)]

    def test_ranges_cover_all_pages_contiguously(self) -> None:
        total = 137
        ranges = _compute_page_ranges(total, 16)
        covered = []
        for start, end in ranges:
            covered.extend(range(start, end + 1))
        assert covered == list(range(1, total + 1))


# ---------------------------------------------------------------------------
# Batched extract_pages
# ---------------------------------------------------------------------------


class TestExtractPagesBatched:
    @pytest.mark.asyncio
    async def test_no_total_pages_uses_single_call(self) -> None:
        """Backward-compatible: no total_pages = single analyze job."""
        book_id = uuid4()
        client = OcrClient("https://test.endpoint", ocr_batch_size=10)

        result = SimpleNamespace(pages=[_make_page(1), _make_page(2)])
        poller = AsyncMock()
        poller.result = AsyncMock(return_value=result)
        mock_di = AsyncMock()
        mock_di.begin_analyze_document = AsyncMock(return_value=poller)
        client._client = mock_di

        pages = await client.extract_pages("https://x/y.pdf", book_id)

        assert [p.page_number for p in pages] == [1, 2]
        assert mock_di.begin_analyze_document.call_count == 1
        # Single-call path should NOT pass a `pages` kwarg.
        _, kwargs = mock_di.begin_analyze_document.call_args
        assert "pages" not in kwargs

    @pytest.mark.asyncio
    async def test_small_doc_uses_single_call(self) -> None:
        """total_pages <= batch_size keeps the single-job path."""
        book_id = uuid4()
        client = OcrClient("https://test.endpoint", ocr_batch_size=10)

        result = SimpleNamespace(pages=[_make_page(i) for i in range(1, 8)])
        poller = AsyncMock()
        poller.result = AsyncMock(return_value=result)
        mock_di = AsyncMock()
        mock_di.begin_analyze_document = AsyncMock(return_value=poller)
        client._client = mock_di

        pages = await client.extract_pages(
            "https://x/y.pdf", book_id, total_pages=7,
        )

        assert len(pages) == 7
        assert mock_di.begin_analyze_document.call_count == 1

    @pytest.mark.asyncio
    async def test_large_doc_splits_into_batches(self) -> None:
        """total_pages > batch_size fans out into concurrent jobs."""
        book_id = uuid4()
        client = OcrClient(
            "https://test.endpoint", ocr_concurrency=3, ocr_batch_size=10,
        )

        # 25 pages → ranges (1-10), (11-20), (21-25)
        # Each batch's result reports pages starting at 1 from Doc Intelligence;
        # the client must apply page_number_offset to get canonical numbering.
        def make_batch_result(n_pages: int):
            return SimpleNamespace(pages=[_make_page(i) for i in range(1, n_pages + 1)])

        # Map blob `pages` arg → result with the right page count.
        batch_results = {
            "1-10": make_batch_result(10),
            "11-20": make_batch_result(10),
            "21-25": make_batch_result(5),
        }

        async def fake_begin(*args, **kwargs):
            pages_arg = kwargs["pages"]
            poller = AsyncMock()
            poller.result = AsyncMock(return_value=batch_results[pages_arg])
            return poller

        mock_di = AsyncMock()
        mock_di.begin_analyze_document = AsyncMock(side_effect=fake_begin)
        client._client = mock_di

        pages = await client.extract_pages(
            "https://x/y.pdf", book_id, total_pages=25,
        )

        # All 25 pages present, in canonical order with no duplicates.
        assert [p.page_number for p in pages] == list(range(1, 26))
        assert mock_di.begin_analyze_document.call_count == 3

        # All calls used the pages kwarg.
        called_pages = sorted(
            call.kwargs["pages"]
            for call in mock_di.begin_analyze_document.call_args_list
        )
        assert called_pages == ["1-10", "11-20", "21-25"]

    @pytest.mark.asyncio
    async def test_concurrency_clamped_by_semaphore(self) -> None:
        """In-flight Document Intelligence jobs never exceed ocr_concurrency."""
        book_id = uuid4()
        client = OcrClient(
            "https://test.endpoint", ocr_concurrency=2, ocr_batch_size=5,
        )

        in_flight = 0
        max_in_flight = 0
        lock = asyncio.Lock()

        async def fake_begin(*args, **kwargs):
            nonlocal in_flight, max_in_flight
            async with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            # Yield so other coroutines can enter the semaphore region too.
            await asyncio.sleep(0.01)

            poller = AsyncMock()
            # 5 pages per batch (last batch may be smaller; fine for this test).
            poller.result = AsyncMock(
                return_value=SimpleNamespace(pages=[_make_page(i) for i in range(1, 6)])
            )

            async def _finish():
                nonlocal in_flight
                async with lock:
                    in_flight -= 1

            # Decrement when poller.result is awaited.
            original_result = poller.result

            async def result_then_finish():
                value = await original_result()
                await _finish()
                return value

            poller.result = result_then_finish
            return poller

        mock_di = AsyncMock()
        mock_di.begin_analyze_document = AsyncMock(side_effect=fake_begin)
        client._client = mock_di

        # 20 pages → 4 batches of 5; concurrency cap is 2.
        await client.extract_pages(
            "https://x/y.pdf", book_id, total_pages=20,
        )
        assert max_in_flight <= 2
        assert mock_di.begin_analyze_document.call_count == 4

    @pytest.mark.asyncio
    async def test_merged_pages_sorted_regardless_of_completion_order(self) -> None:
        """If later batches resolve first, merged output is still in order."""
        book_id = uuid4()
        client = OcrClient(
            "https://test.endpoint", ocr_concurrency=4, ocr_batch_size=5,
        )

        async def fake_begin(*args, **kwargs):
            pages_arg = kwargs["pages"]
            # Earliest-page batches sleep longest so they finish last.
            start = int(pages_arg.split("-")[0])
            sleep_s = 0.05 if start == 1 else 0.0

            async def result_coro():
                if sleep_s:
                    await asyncio.sleep(sleep_s)
                return SimpleNamespace(pages=[_make_page(i) for i in range(1, 6)])

            poller = AsyncMock()
            poller.result = result_coro
            return poller

        mock_di = AsyncMock()
        mock_di.begin_analyze_document = AsyncMock(side_effect=fake_begin)
        client._client = mock_di

        pages = await client.extract_pages(
            "https://x/y.pdf", book_id, total_pages=15,
        )
        assert [p.page_number for p in pages] == list(range(1, 16))

    def test_init_clamps_invalid_values(self) -> None:
        """Negative/zero knobs are clamped to safe minimums."""
        c = OcrClient("https://x", ocr_concurrency=0, ocr_batch_size=-3)
        assert c._ocr_concurrency == 1
        assert c._ocr_batch_size == 1
