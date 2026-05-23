"""Append-only stage-level cost telemetry events (closes #97 / #93).

Each pipeline invocation generates a fresh ``run_id``. For every stage the
runner executes, two writes occur:

* ``record_stage_start`` inserts a row with ``status='started'`` and
  ``ended_at IS NULL`` so interrupted runs leave forensic evidence behind.
* ``record_stage_end`` updates that row with the per-stage metrics delta
  and a terminal status (``completed`` or ``failed``).

All writes are best-effort: telemetry must never block the pipeline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


@dataclass
class StageMetricsDelta:
    """Per-stage usage delta captured at stage completion."""

    input_tokens: int = 0
    output_tokens: int = 0
    ocr_pages: int = 0
    blob_read_ops: int = 0
    blob_write_ops: int = 0
    estimated_cost_usd: float = 0.0
    retries: int = 0


def _coerce_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def record_stage_start(
    db: Any,
    *,
    book_id: Any,
    run_id: UUID,
    stage_name: str,
    started_at: datetime | None = None,
) -> UUID | None:
    """Insert a ``status='started'`` event row, return its event id.

    Returns ``None`` if ``book_id`` is not yet known or the INSERT fails;
    callers may pass the returned id to ``record_stage_end`` (which is a
    no-op when given ``None``).
    """
    book_uuid = _coerce_uuid(book_id)
    if book_uuid is None:
        return None
    event_id = uuid4()
    when = started_at or datetime.now(UTC)
    try:
        await db.execute(
            """
            INSERT INTO book_cost_events
                (id, book_id, run_id, stage_name, started_at, status)
            VALUES ($1, $2, $3, $4, $5, 'started')
            """,
            event_id,
            book_uuid,
            run_id,
            stage_name,
            when,
        )
        return event_id
    except Exception as exc:  # pragma: no cover - logged, never raised
        logger.warning(
            "cost_events: record_stage_start failed for stage=%s book=%s: %s",
            stage_name,
            book_uuid,
            exc,
        )
        return None


async def record_stage_end(
    db: Any,
    event_id: UUID | None,
    *,
    status: str = "completed",
    ended_at: datetime | None = None,
    metrics: StageMetricsDelta | None = None,
    error_message: str | None = None,
) -> None:
    """Finalize a started event with metrics and terminal status.

    Best-effort: swallows exceptions so telemetry never breaks a pipeline run.
    """
    if event_id is None:
        return
    when = ended_at or datetime.now(UTC)
    m = metrics or StageMetricsDelta()
    try:
        await db.execute(
            """
            UPDATE book_cost_events
            SET ended_at = $1,
                status = $2,
                input_tokens = $3,
                output_tokens = $4,
                ocr_pages = $5,
                blob_read_ops = $6,
                blob_write_ops = $7,
                estimated_cost_usd = $8,
                retries = $9,
                error_message = $10
            WHERE id = $11
            """,
            when,
            status,
            int(m.input_tokens),
            int(m.output_tokens),
            int(m.ocr_pages),
            int(m.blob_read_ops),
            int(m.blob_write_ops),
            float(m.estimated_cost_usd),
            int(m.retries),
            error_message,
            event_id,
        )
    except Exception as exc:  # pragma: no cover - logged, never raised
        logger.warning(
            "cost_events: record_stage_end failed for event=%s: %s", event_id, exc
        )


def snapshot_tracker(tracker: Any) -> dict[str, float]:
    """Capture CostTracker accumulated counters as a plain dict."""
    if tracker is None:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "pages": 0,
            "blob_reads": 0,
            "blob_writes": 0,
            "cost_usd": 0.0,
        }
    summary = tracker.summary()
    return {
        "input_tokens": summary.openai_input_tokens,
        "output_tokens": summary.openai_output_tokens,
        "pages": summary.ocr_pages,
        "blob_reads": summary.blob_read_ops,
        "blob_writes": summary.blob_write_ops,
        "cost_usd": summary.total_cost_usd,
    }


def delta(before: dict[str, float], after: dict[str, float]) -> StageMetricsDelta:
    """Compute non-negative deltas between two tracker snapshots."""
    return StageMetricsDelta(
        input_tokens=max(0, int(after["input_tokens"]) - int(before["input_tokens"])),
        output_tokens=max(0, int(after["output_tokens"]) - int(before["output_tokens"])),
        ocr_pages=max(0, int(after["pages"]) - int(before["pages"])),
        blob_read_ops=max(0, int(after["blob_reads"]) - int(before["blob_reads"])),
        blob_write_ops=max(0, int(after["blob_writes"]) - int(before["blob_writes"])),
        estimated_cost_usd=max(0.0, float(after["cost_usd"]) - float(before["cost_usd"])),
    )
