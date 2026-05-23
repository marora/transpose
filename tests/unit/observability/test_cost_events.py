"""Unit tests for stage-level cost events module (#97 / #101)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from transpose.observability import cost_events
from transpose.observability.cost_events import StageMetricsDelta


class _FakeDB:
    """Records every execute() call so tests can assert SQL params."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._fail_on = fail_on

    async def execute(self, query: str, *args) -> None:
        if self._fail_on and self._fail_on in query:
            raise RuntimeError("simulated DB failure")
        self.calls.append((query, args))


class _FakeSummary:
    def __init__(self, **kwargs) -> None:
        defaults = {
            "openai_input_tokens": 0,
            "openai_output_tokens": 0,
            "ocr_pages": 0,
            "blob_read_ops": 0,
            "blob_write_ops": 0,
            "total_cost_usd": 0.0,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


class _FakeTracker:
    def __init__(self, **kwargs) -> None:
        self._summary = _FakeSummary(**kwargs)

    def summary(self) -> _FakeSummary:
        return self._summary


class TestRecordStageStart:
    @pytest.mark.asyncio
    async def test_inserts_started_row(self) -> None:
        db = _FakeDB()
        book_id = uuid4()
        run_id = uuid4()
        when = datetime(2026, 5, 24, 12, 0, 0)

        event_id = await cost_events.record_stage_start(
            db, book_id=book_id, run_id=run_id, stage_name="ingest", started_at=when
        )

        assert isinstance(event_id, UUID)
        assert len(db.calls) == 1
        query, args = db.calls[0]
        assert "INSERT INTO book_cost_events" in query
        assert "'started'" in query
        assert args == (event_id, book_id, run_id, "ingest", when)

    @pytest.mark.asyncio
    async def test_string_book_id_is_coerced(self) -> None:
        db = _FakeDB()
        book_id = uuid4()
        event_id = await cost_events.record_stage_start(
            db, book_id=str(book_id), run_id=uuid4(), stage_name="ocr"
        )
        assert event_id is not None
        assert db.calls[0][1][1] == book_id

    @pytest.mark.asyncio
    async def test_none_book_id_is_noop(self) -> None:
        db = _FakeDB()
        result = await cost_events.record_stage_start(
            db, book_id=None, run_id=uuid4(), stage_name="ingest"
        )
        assert result is None
        assert db.calls == []

    @pytest.mark.asyncio
    async def test_invalid_book_id_is_noop(self) -> None:
        db = _FakeDB()
        result = await cost_events.record_stage_start(
            db, book_id="not-a-uuid", run_id=uuid4(), stage_name="ingest"
        )
        assert result is None
        assert db.calls == []

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed(self) -> None:
        db = _FakeDB(fail_on="INSERT")
        result = await cost_events.record_stage_start(
            db, book_id=uuid4(), run_id=uuid4(), stage_name="ingest"
        )
        assert result is None


class TestRecordStageEnd:
    @pytest.mark.asyncio
    async def test_updates_with_metrics(self) -> None:
        db = _FakeDB()
        event_id = uuid4()
        metrics = StageMetricsDelta(
            input_tokens=120,
            output_tokens=80,
            ocr_pages=18,
            blob_read_ops=3,
            blob_write_ops=2,
            estimated_cost_usd=0.0421,
            retries=1,
        )
        when = datetime(2026, 5, 24, 12, 5, 0)

        await cost_events.record_stage_end(
            db, event_id, status="completed", ended_at=when, metrics=metrics
        )

        assert len(db.calls) == 1
        query, args = db.calls[0]
        assert "UPDATE book_cost_events" in query
        assert args[0] == when
        assert args[1] == "completed"
        assert args[2] == 120  # input_tokens
        assert args[3] == 80  # output_tokens
        assert args[4] == 18  # ocr_pages
        assert args[5] == 3  # blob_read_ops
        assert args[6] == 2  # blob_write_ops
        assert args[7] == pytest.approx(0.0421)
        assert args[8] == 1  # retries
        assert args[9] is None  # error_message
        assert args[10] == event_id

    @pytest.mark.asyncio
    async def test_failed_status_records_error(self) -> None:
        db = _FakeDB()
        event_id = uuid4()
        await cost_events.record_stage_end(
            db, event_id, status="failed", error_message="boom"
        )
        assert db.calls[0][1][1] == "failed"
        assert db.calls[0][1][9] == "boom"

    @pytest.mark.asyncio
    async def test_none_event_id_is_noop(self) -> None:
        db = _FakeDB()
        await cost_events.record_stage_end(db, None, status="completed")
        assert db.calls == []

    @pytest.mark.asyncio
    async def test_db_failure_is_swallowed(self) -> None:
        db = _FakeDB(fail_on="UPDATE")
        # Should not raise even though the UPDATE fails
        await cost_events.record_stage_end(db, uuid4(), status="completed")


class TestSnapshotAndDelta:
    def test_snapshot_none_tracker_returns_zeros(self) -> None:
        snap = cost_events.snapshot_tracker(None)
        assert snap["input_tokens"] == 0
        assert snap["cost_usd"] == 0.0

    def test_snapshot_reads_tracker_summary(self) -> None:
        tracker = _FakeTracker(
            openai_input_tokens=500,
            openai_output_tokens=300,
            ocr_pages=10,
            blob_read_ops=4,
            blob_write_ops=2,
            total_cost_usd=0.123,
        )
        snap = cost_events.snapshot_tracker(tracker)
        assert snap == {
            "input_tokens": 500,
            "output_tokens": 300,
            "pages": 10,
            "blob_reads": 4,
            "blob_writes": 2,
            "cost_usd": 0.123,
        }

    def test_delta_computes_positive_difference(self) -> None:
        before = {
            "input_tokens": 100,
            "output_tokens": 50,
            "pages": 5,
            "blob_reads": 1,
            "blob_writes": 1,
            "cost_usd": 0.01,
        }
        after = {
            "input_tokens": 350,
            "output_tokens": 200,
            "pages": 12,
            "blob_reads": 4,
            "blob_writes": 3,
            "cost_usd": 0.045,
        }
        d = cost_events.delta(before, after)
        assert d.input_tokens == 250
        assert d.output_tokens == 150
        assert d.ocr_pages == 7
        assert d.blob_read_ops == 3
        assert d.blob_write_ops == 2
        assert d.estimated_cost_usd == pytest.approx(0.035)

    def test_delta_clamps_negative_to_zero(self) -> None:
        # Should never go negative even if counters reset mid-run
        before = {
            "input_tokens": 100,
            "output_tokens": 50,
            "pages": 5,
            "blob_reads": 1,
            "blob_writes": 1,
            "cost_usd": 0.1,
        }
        after = dict(before)
        after["input_tokens"] = 0
        after["cost_usd"] = 0.0
        d = cost_events.delta(before, after)
        assert d.input_tokens == 0
        assert d.estimated_cost_usd == 0.0


class TestInterruptedRunSemantics:
    """Verify the contract that interrupted runs leave forensic rows."""

    @pytest.mark.asyncio
    async def test_started_row_persists_when_end_never_called(self) -> None:
        db = _FakeDB()
        await cost_events.record_stage_start(
            db, book_id=uuid4(), run_id=uuid4(), stage_name="translate"
        )
        # Simulate process crash: no record_stage_end ever fires
        assert len(db.calls) == 1
        query, _ = db.calls[0]
        assert "INSERT" in query
        # The row has status='started' and ended_at IS NULL by schema default
        # — no UPDATE was issued, so the forensic row remains.
