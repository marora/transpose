"""Unit tests for the cost & wall-time projector (#99 / #101)."""

from __future__ import annotations

import pytest

from transpose.observability.projector import (
    ProjectionResult,
    StagePerBookSample,
    estimate,
)


def _sample(book_id: str, stage: str, *, cost: float, dur: float, pages: int) -> StagePerBookSample:
    return StagePerBookSample(
        book_id=book_id, stage_name=stage,
        cost_usd=cost, duration_seconds=dur, pages=pages,
    )


class TestEstimateBasics:
    def test_empty_history_returns_none_confidence(self) -> None:
        result = estimate([], pages=100)
        assert isinstance(result, ProjectionResult)
        assert result.confidence == "none"
        assert result.sample_book_count == 0
        assert result.stages == []
        assert result.total_cost_usd == 0.0
        assert result.total_duration_seconds == 0.0

    def test_one_book_low_confidence(self) -> None:
        history = [
            _sample("b1", "translate", cost=1.0, dur=600.0, pages=100),
            _sample("b1", "ocr", cost=0.5, dur=200.0, pages=100),
        ]
        result = estimate(history, pages=200)
        assert result.confidence == "low"
        assert result.sample_book_count == 1
        # Linear scaling: 200 pages → 2× per-book cost.
        translate = next(s for s in result.stages if s.stage_name == "translate")
        assert translate.estimated_cost_usd == pytest.approx(2.0)
        assert translate.estimated_duration_seconds == pytest.approx(1200.0)
        assert translate.sample_size == 1

    def test_two_books_medium_confidence(self) -> None:
        history = [
            _sample("b1", "translate", cost=1.0, dur=600.0, pages=100),
            _sample("b2", "translate", cost=2.0, dur=1200.0, pages=200),
        ]
        result = estimate(history, pages=150)
        assert result.confidence == "medium"
        assert result.sample_book_count == 2
        # cost_per_page: 0.01 and 0.01, median = 0.01, ×150 = 1.5
        assert result.total_cost_usd == pytest.approx(1.5)

    def test_three_books_high_confidence_uses_median(self) -> None:
        history = [
            _sample("b1", "translate", cost=1.0, dur=500.0, pages=100),
            _sample("b2", "translate", cost=3.0, dur=1500.0, pages=100),
            # outlier
            _sample("b3", "translate", cost=10.0, dur=5000.0, pages=100),
        ]
        result = estimate(history, pages=100)
        assert result.confidence == "high"
        # median(0.01, 0.03, 0.10) = 0.03 → 0.03 * 100 = 3.0
        translate = result.stages[0]
        assert translate.estimated_cost_usd == pytest.approx(3.0)
        assert translate.estimated_duration_seconds == pytest.approx(1500.0)


class TestEstimateEdgeCases:
    def test_zero_cost_stage_projects_zero_cost(self) -> None:
        """Ingest / chunk have zero cost but real duration."""
        history = [
            _sample("b1", "ingest", cost=0.0, dur=12.0, pages=100),
            _sample("b1", "chunk", cost=0.0, dur=8.0, pages=100),
        ]
        result = estimate(history, pages=250)
        ingest = next(s for s in result.stages if s.stage_name == "ingest")
        assert ingest.estimated_cost_usd == 0.0
        assert ingest.estimated_duration_seconds == pytest.approx(30.0)

    def test_invalid_pages_raises(self) -> None:
        with pytest.raises(ValueError):
            estimate([], pages=0)
        with pytest.raises(ValueError):
            estimate([], pages=-5)

    def test_zero_page_samples_are_skipped(self) -> None:
        """A historical book with page_count=0 must not divide-by-zero."""
        history = [
            _sample("b1", "translate", cost=1.0, dur=600.0, pages=0),
            _sample("b2", "translate", cost=2.0, dur=1200.0, pages=200),
        ]
        result = estimate(history, pages=100)
        assert result.sample_book_count == 1  # only b2 contributed
        assert result.confidence == "low"

    def test_stages_sorted_alphabetically(self) -> None:
        history = [
            _sample("b1", "translate", cost=1.0, dur=600.0, pages=100),
            _sample("b1", "ingest", cost=0.0, dur=10.0, pages=100),
            _sample("b1", "ocr", cost=0.5, dur=300.0, pages=100),
        ]
        result = estimate(history, pages=100)
        names = [s.stage_name for s in result.stages]
        assert names == sorted(names)

    def test_total_is_sum_of_stage_estimates(self) -> None:
        history = [
            _sample("b1", "translate", cost=1.0, dur=600.0, pages=100),
            _sample("b1", "ocr", cost=0.5, dur=200.0, pages=100),
        ]
        result = estimate(history, pages=50)
        assert result.total_cost_usd == pytest.approx(
            sum(s.estimated_cost_usd for s in result.stages)
        )
        assert result.total_duration_seconds == pytest.approx(
            sum(s.estimated_duration_seconds for s in result.stages)
        )
