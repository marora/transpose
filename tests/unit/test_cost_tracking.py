"""Tests for cost tracking: rates, tracker, and database persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from transpose.observability.cost_rates import DEFAULT_RATES, CostRates
from transpose.observability.cost_tracker import CostTracker

# --- CostRates tests ---


class TestCostRates:
    def test_default_rates_exist(self):
        assert DEFAULT_RATES.openai_input_per_1k > 0
        assert DEFAULT_RATES.openai_output_per_1k > 0
        assert DEFAULT_RATES.doc_intelligence_per_page > 0

    def test_estimate_openai_cost(self):
        rates = CostRates(openai_input_per_1k=0.005, openai_output_per_1k=0.015)
        cost = rates.estimate_openai_cost(prompt_tokens=1000, completion_tokens=1000)
        assert cost == pytest.approx(0.020, abs=1e-6)

    def test_estimate_openai_cost_zero(self):
        assert DEFAULT_RATES.estimate_openai_cost(0, 0) == 0.0

    def test_estimate_ocr_cost(self):
        rates = CostRates(doc_intelligence_per_page=0.01)
        assert rates.estimate_ocr_cost(100) == pytest.approx(1.0)

    def test_estimate_ocr_cost_zero(self):
        assert DEFAULT_RATES.estimate_ocr_cost(0) == 0.0

    def test_estimate_blob_cost(self):
        rates = CostRates(blob_write_per_10k=0.05, blob_read_per_10k=0.004)
        cost = rates.estimate_blob_cost(write_ops=10_000, read_ops=10_000)
        assert cost == pytest.approx(0.054)

    def test_custom_rates(self):
        rates = CostRates(openai_input_per_1k=0.01, openai_output_per_1k=0.03)
        cost = rates.estimate_openai_cost(500, 200)
        expected = (500 / 1000) * 0.01 + (200 / 1000) * 0.03
        assert cost == pytest.approx(expected)

    def test_frozen_dataclass(self):
        with pytest.raises(AttributeError):
            DEFAULT_RATES.openai_input_per_1k = 999


# --- CostTracker tests ---


class TestCostTracker:
    def test_empty_tracker_summary(self):
        tracker = CostTracker(uuid4())
        s = tracker.summary()
        assert s.total_cost_usd == 0.0
        assert s.openai_input_tokens == 0
        assert s.ocr_pages == 0

    def test_record_llm_usage(self):
        tracker = CostTracker(uuid4())
        tracker.record_llm_usage(prompt_tokens=1000, completion_tokens=500)
        tracker.record_llm_usage(prompt_tokens=2000, completion_tokens=1000)
        s = tracker.summary()
        assert s.openai_input_tokens == 3000
        assert s.openai_output_tokens == 1500

    def test_record_ocr_pages(self):
        tracker = CostTracker(uuid4())
        tracker.record_ocr_pages(18)
        s = tracker.summary()
        assert s.ocr_pages == 18
        assert s.ocr_cost_usd == pytest.approx(0.18)

    def test_record_blob_operations(self):
        tracker = CostTracker(uuid4())
        tracker.record_blob_operation("write")
        tracker.record_blob_operation("write")
        tracker.record_blob_operation("read")
        tracker.record_blob_operation("invalid")  # ignored
        s = tracker.summary()
        assert s.blob_write_ops == 2
        assert s.blob_read_ops == 1

    def test_total_cost_is_sum(self):
        rates = CostRates(
            openai_input_per_1k=0.005,
            openai_output_per_1k=0.015,
            doc_intelligence_per_page=0.01,
            blob_write_per_10k=0.05,
            blob_read_per_10k=0.004,
        )
        tracker = CostTracker(uuid4(), rates=rates)
        tracker.record_llm_usage(1000, 1000)
        tracker.record_ocr_pages(10)
        tracker.record_blob_operation("write")

        s = tracker.summary()
        expected_openai = 0.005 + 0.015
        expected_ocr = 0.10
        expected_blob = 1 / 10_000 * 0.05
        assert s.total_cost_usd == pytest.approx(
            expected_openai + expected_ocr + expected_blob
        )

    def test_book_id_preserved(self):
        bid = uuid4()
        tracker = CostTracker(bid)
        assert tracker.book_id == bid
        assert tracker.summary().book_id == bid

    @pytest.mark.asyncio
    async def test_persist_calls_db(self):
        db = AsyncMock()
        db.save_book_costs = AsyncMock()

        tracker = CostTracker(uuid4())
        tracker.record_llm_usage(500, 200)
        tracker.record_ocr_pages(5)

        await tracker.persist(db)

        db.save_book_costs.assert_called_once()
        call_args = db.save_book_costs.call_args
        book_id_arg = call_args[0][0]
        rows_arg = call_args[0][1]

        assert book_id_arg == tracker.book_id
        # Should have rows for: input_tokens, output_tokens, pages
        services = [r[0] for r in rows_arg]
        assert "openai" in services
        assert "doc_intelligence" in services

    @pytest.mark.asyncio
    async def test_persist_skips_zero_usage(self):
        db = AsyncMock()
        db.save_book_costs = AsyncMock()

        tracker = CostTracker(uuid4())
        # Record only LLM, no OCR or blob
        tracker.record_llm_usage(100, 50)

        await tracker.persist(db)

        rows = db.save_book_costs.call_args[0][1]
        services = [r[0] for r in rows]
        assert "doc_intelligence" not in services
        assert "blob_storage" not in services

    @pytest.mark.asyncio
    async def test_persist_empty_tracker_no_db_call(self):
        db = AsyncMock()
        db.save_book_costs = AsyncMock()

        tracker = CostTracker(uuid4())
        await tracker.persist(db)

        db.save_book_costs.assert_not_called()

    def test_realistic_book_cost(self):
        """Simulates a 95-chapter book translation."""
        tracker = CostTracker(uuid4())
        # ~95 chunks, avg 1500 input tokens, 1200 output tokens each
        for _ in range(95):
            tracker.record_llm_usage(prompt_tokens=1500, completion_tokens=1200)
        tracker.record_ocr_pages(300)
        for _ in range(3):  # PDF upload + ePub + PDF export
            tracker.record_blob_operation("write")

        s = tracker.summary()
        # 95 * (1500*0.005/1000 + 1200*0.015/1000) = 95 * (0.0075 + 0.018) = 95 * 0.0255 = ~2.42
        assert s.openai_cost_usd == pytest.approx(2.4225, rel=0.01)
        assert s.ocr_cost_usd == pytest.approx(3.0)
        assert s.total_cost_usd > 5
        assert s.ocr_pages == 300
