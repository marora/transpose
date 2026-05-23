"""Cost & wall-time projector for upcoming pipeline runs (#99).

Given historical stage events for the last few completed books, estimate
cost & duration for a book of ``N`` pages by linear scaling per stage.

Pure function — caller supplies historical data; this module performs no
I/O. The dashboard API does the DB query, then hands rows to ``estimate``.

Confidence ladder:
* 3+ books → ``high``
* 2 books  → ``medium``
* 1 book   → ``low``
* 0 books  → ``none`` (empty result)
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median


@dataclass
class StagePerBookSample:
    """One historical (book_id, stage, totals, pages) datapoint."""

    book_id: str
    stage_name: str
    cost_usd: float
    duration_seconds: float
    pages: int


@dataclass
class StageProjection:
    stage_name: str
    estimated_cost_usd: float
    estimated_duration_seconds: float
    sample_size: int


@dataclass
class ProjectionResult:
    pages: int
    confidence: str  # "none" | "low" | "medium" | "high"
    sample_book_count: int
    stages: list[StageProjection]
    total_cost_usd: float
    total_duration_seconds: float


def _confidence(book_count: int) -> str:
    if book_count >= 3:
        return "high"
    if book_count == 2:
        return "medium"
    if book_count == 1:
        return "low"
    return "none"


def estimate(
    samples: list[StagePerBookSample],
    *,
    pages: int,
    rolling_window: int = 3,
) -> ProjectionResult:
    """Estimate cost + duration for a book of ``pages`` pages.

    ``samples`` must contain at most ``rolling_window`` distinct books; if
    the caller passes more, the result is still valid but the confidence
    label still reads from the distinct-book count.

    For each stage, take the median of ``cost_per_page`` and
    ``seconds_per_page`` across the historical books, then multiply by
    ``pages``. Stages with zero historical cost (e.g. ``ingest`` or
    ``chunk``) project to zero cost but keep their duration estimate.
    """
    if pages <= 0:
        raise ValueError("pages must be > 0")

    by_stage: dict[str, list[StagePerBookSample]] = {}
    distinct_books: set[str] = set()
    for s in samples:
        if s.pages <= 0:
            continue
        by_stage.setdefault(s.stage_name, []).append(s)
        distinct_books.add(s.book_id)

    book_count = len(distinct_books)
    projections: list[StageProjection] = []
    total_cost = 0.0
    total_duration = 0.0

    for stage_name, rows in by_stage.items():
        cost_per_page = [r.cost_usd / r.pages for r in rows]
        sec_per_page = [r.duration_seconds / r.pages for r in rows]
        est_cost = median(cost_per_page) * pages
        est_dur = median(sec_per_page) * pages
        projections.append(
            StageProjection(
                stage_name=stage_name,
                estimated_cost_usd=round(est_cost, 6),
                estimated_duration_seconds=round(est_dur, 3),
                sample_size=len(rows),
            )
        )
        total_cost += est_cost
        total_duration += est_dur

    projections.sort(key=lambda p: p.stage_name)

    return ProjectionResult(
        pages=pages,
        confidence=_confidence(book_count),
        sample_book_count=book_count,
        stages=projections,
        total_cost_usd=round(total_cost, 6),
        total_duration_seconds=round(total_duration, 3),
    )
