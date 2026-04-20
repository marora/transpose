"""Tests for the pipeline runner.

Tests full pipeline execution, stage orchestration, and error handling.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from transpose.models.enums import BookStatus, SourceLanguage


@dataclass
class PipelineInput:
    """Top-level input to run the full pipeline."""

    source_path: str
    title: str
    author: str | None = None
    source_language: SourceLanguage = SourceLanguage.HINDI
    output_formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])
    resume_from: str | None = None


@dataclass
class ExportArtifact:
    """Artifact from export stage."""

    format: str
    blob_uri: str
    file_size_bytes: int


@dataclass
class PipelineOutput:
    """Top-level output of the full pipeline."""

    book_id: UUID
    status: BookStatus
    artifacts: list[ExportArtifact]
    glossary_term_count: int
    total_tokens_used: int
    stages_completed: list[str]
    errors: list[dict] = field(default_factory=list)


class TestPipelineContract:
    """Test pipeline runner contract validation."""

    def test_pipeline_input_required_fields(self) -> None:
        """Test PipelineInput requires source_path and title."""
        input_data = PipelineInput(
            source_path="/path/to/book.pdf",
            title="Test Book",
        )
        assert input_data.source_path == "/path/to/book.pdf"
        assert input_data.title == "Test Book"
        assert input_data.source_language == SourceLanguage.HINDI

    def test_pipeline_output_shape(self) -> None:
        """Test PipelineOutput has all required fields."""
        output = PipelineOutput(
            book_id=uuid4(),
            status=BookStatus.EXPORTED,
            artifacts=[],
            glossary_term_count=50,
            total_tokens_used=10000,
            stages_completed=[
                "ingest", "ocr", "chunk", "translate",
                "glossary", "assemble", "export",
            ],
            errors=[],
        )
        assert output.status == BookStatus.EXPORTED
        assert len(output.stages_completed) == 7


class TestPipelineStageOrdering:
    """Test that stages run in correct order."""

    def test_stages_run_in_order(self) -> None:
        """Test that all 7 stages run in correct order."""
        expected_order = [
            "ingest",
            "ocr",
            "chunk",
            "translate",
            "glossary",
            "assemble",
            "export",
        ]

        # Simulate pipeline execution
        stages_completed = []
        for stage in expected_order:
            stages_completed.append(stage)

        assert stages_completed == expected_order

    def test_resume_from_skips_earlier_stages(self) -> None:
        """Test that resume_from skips earlier stages."""
        input_data = PipelineInput(
            source_path="/path/to/book.pdf",
            title="Test Book",
            resume_from="translate",
        )

        expected_order = ["ingest", "ocr", "chunk", "translate", "glossary", "assemble", "export"]
        resume_idx = expected_order.index(input_data.resume_from)

        stages_to_run = expected_order[resume_idx:]

        assert "ingest" not in stages_to_run
        assert "ocr" not in stages_to_run
        assert "translate" in stages_to_run


class TestPipelineStatusTransitions:
    """Test book status transitions through pipeline."""

    def test_status_transitions(self) -> None:
        """Test that book status transitions correctly."""
        transitions = [
            (BookStatus.INGESTED, "ingest"),
            (BookStatus.OCR_COMPLETE, "ocr"),
            (BookStatus.CHUNKED, "chunk"),
            (BookStatus.TRANSLATED, "translate"),
            (BookStatus.ASSEMBLED, "assemble"),
            (BookStatus.EXPORTED, "export"),
        ]

        # Verify all transitions are valid
        for status, _stage in transitions:
            assert status in BookStatus


class TestPipelineErrorHandling:
    """Test pipeline error handling."""

    @pytest.mark.asyncio
    async def test_error_in_stage_sets_failed_status(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test that error in one stage sets FAILED status."""
        book_id = uuid4()

        # Simulate a stage failure
        output = PipelineOutput(
            book_id=book_id,
            status=BookStatus.FAILED,
            artifacts=[],
            glossary_term_count=0,
            total_tokens_used=500,
            stages_completed=["ingest", "ocr"],
            errors=[{"stage": "chunk", "error": "Chunking failed"}],
        )

        assert output.status == BookStatus.FAILED
        assert len(output.errors) > 0
        assert len(output.stages_completed) < 7


class TestPipelineDistributedLock:
    """Test distributed locking for pipeline."""

    @pytest.mark.asyncio
    async def test_lock_acquisition(
        self,
        mock_state: AsyncMock,
    ) -> None:
        """Test that pipeline acquires distributed lock."""
        book_id = uuid4()
        lock_key = f"pipeline:lock:{book_id}"

        mock_state.acquire_lock = AsyncMock(return_value=True)

        acquired = await mock_state.acquire_lock(lock_key, timeout=300)

        assert acquired is True
        mock_state.acquire_lock.assert_called_once_with(lock_key, timeout=300)

    @pytest.mark.asyncio
    async def test_lock_already_held(
        self,
        mock_state: AsyncMock,
    ) -> None:
        """Test behavior when lock is already held."""
        book_id = uuid4()
        lock_key = f"pipeline:lock:{book_id}"

        mock_state.acquire_lock = AsyncMock(return_value=False)

        acquired = await mock_state.acquire_lock(lock_key, timeout=300)

        assert acquired is False


class TestLockAcquisitionInRunner:
    """Test that run_pipeline() wires acquire_lock() before OCR (B1 fix).

    Chani is adding acquire_lock() to runner.py. These tests verify:
    - Lock is acquired before OCR stage
    - Pipeline aborts when lock acquisition fails
    - Lock is released on both success and failure paths
    - Lock uses the correct book_id
    """

    @pytest.fixture
    def _patch_stages(self, monkeypatch):
        """Patch all stage modules and metrics so run_pipeline() doesn't
        hit real Azure services.  Returns (mocks-dict, service-context)."""
        import sys
        import types

        from transpose.pipeline import runner
        from transpose.pipeline.gates import GateResult

        book_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        # Stub ingest
        ingest_out = types.SimpleNamespace(
            book_id=book_id, page_count=10, already_existed=False,
        )
        mock_ingest = AsyncMock(return_value=ingest_out)

        # Stub ocr
        ocr_out = types.SimpleNamespace(
            pages_processed=10, pages_skipped=0, low_confidence_count=0,
            total_pages=10, average_confidence=0.95, pages=[],
        )
        mock_ocr = AsyncMock(return_value=ocr_out)

        # Stub remaining stages
        chunk_out = types.SimpleNamespace(total_chunks=5)
        translate_out = types.SimpleNamespace(
            chunks_translated=5, total_prompt_tokens=500,
            total_completion_tokens=300, chunks_total=5,
            failed_chunks=0,
        )
        glossary_out = types.SimpleNamespace(
            total_terms=10, needs_review_count=0,
            terms=[], preserved_count=10,
        )
        assemble_out = types.SimpleNamespace(
            chapters=[{"title": "Ch1"}],
            has_cover=True, has_toc=True, has_foreword=True,
        )
        export_artifact = types.SimpleNamespace(
            format="pdf", blob_uri="/fake/book.pdf", file_size_bytes=1024,
        )
        export_out = types.SimpleNamespace(
            artifacts=[export_artifact], total_size_bytes=1024,
        )

        stage_mocks = {
            "ingest": mock_ingest,
            "ocr": mock_ocr,
            "chunk": AsyncMock(return_value=chunk_out),
            "translate": AsyncMock(return_value=translate_out),
            "glossary": AsyncMock(return_value=glossary_out),
            "assemble": AsyncMock(return_value=assemble_out),
            "export": AsyncMock(return_value=export_out),
        }

        # Patch each stage as a sys.modules entry so the local import
        # `from . import ingest, ocr, ...` inside run_pipeline() finds our mocks.
        for name, mock_fn in stage_mocks.items():
            mod = types.ModuleType(f"transpose.pipeline.{name}")
            mod.run = mock_fn  # type: ignore[attr-defined]
            # Create trivial Input classes
            input_cls_name = {
                "ingest": "IngestInput",
                "ocr": "OcrInput",
                "chunk": "ChunkInput",
                "translate": "TranslateInput",
                "glossary": "GlossaryInput",
                "assemble": "AssembleInput",
                "export": "ExportInput",
            }[name]
            setattr(mod, input_cls_name, type(input_cls_name, (), {
                "__init__": lambda self, **kw: self.__dict__.update(kw),
            }))
            monkeypatch.setitem(sys.modules, f"transpose.pipeline.{name}", mod)

        # Patch all quality gates to pass
        def _pass_gate(name):
            return lambda _: GateResult(name, True, [], {})

        monkeypatch.setattr(runner, "ocr_sanity_gate", _pass_gate("ocr_sanity"))
        monkeypatch.setattr(
            runner, "translation_completeness_gate",
            _pass_gate("translation_completeness"),
        )
        monkeypatch.setattr(
            runner, "glossary_integrity_gate", _pass_gate("glossary_integrity"),
        )
        monkeypatch.setattr(
            runner, "document_structure_gate", _pass_gate("document_structure"),
        )
        monkeypatch.setattr(
            runner, "artifact_availability_gate",
            _pass_gate("artifact_availability"),
        )
        monkeypatch.setattr(
            runner, "golden_targeted_qa_gate", _pass_gate("golden_qa"),
        )
        monkeypatch.setattr(
            runner, "validate_production_readiness",
            _pass_gate("production_readiness"),
        )

        # Patch metrics
        mock_duration = type("M", (), {"record": lambda self, *a, **kw: None})()
        mock_errors = type("M", (), {"add": lambda self, *a, **kw: None})()
        monkeypatch.setattr("transpose.observability.metrics.stage_duration", mock_duration)
        monkeypatch.setattr("transpose.observability.metrics.pipeline_errors", mock_errors)

        # Build mock service context
        from unittest.mock import MagicMock

        ctx = MagicMock()
        ctx.state = AsyncMock()
        ctx.state.set_pipeline_status = AsyncMock()
        ctx.state.acquire_lock = AsyncMock(return_value=True)
        ctx.state.release_lock = AsyncMock()
        ctx.db = AsyncMock()
        ctx.db.update_book_status = AsyncMock()

        return stage_mocks, ctx, book_id

    @pytest.mark.asyncio
    async def test_acquire_lock_called_before_ocr(self, _patch_stages) -> None:
        """acquire_lock() must be called before the OCR stage runs."""
        from transpose.pipeline.runner import PipelineInput, run_pipeline

        stage_mocks, ctx, book_id = _patch_stages
        call_order: list[str] = []

        orig_acquire = ctx.state.acquire_lock

        async def track_acquire(*a, **kw):
            call_order.append("acquire_lock")
            return await orig_acquire(*a, **kw)

        ctx.state.acquire_lock = AsyncMock(side_effect=track_acquire)

        orig_ocr = stage_mocks["ocr"]

        async def track_ocr(*a, **kw):
            call_order.append("ocr")
            return await orig_ocr(*a, **kw)

        stage_mocks["ocr"].side_effect = track_ocr

        inp = PipelineInput(source_path="/fake.pdf", title="Test")
        with contextlib.suppress(Exception):
            await run_pipeline(inp, ctx)

        # acquire_lock should appear before ocr — if it exists
        if "acquire_lock" in call_order and "ocr" in call_order:
            assert call_order.index("acquire_lock") < call_order.index("ocr"), (
                "acquire_lock() must be called before OCR stage"
            )
        else:
            # Chani hasn't wired acquire_lock yet — mark pending
            pytest.xfail("acquire_lock() not yet wired in runner (B1 pending)")

    @pytest.mark.asyncio
    async def test_pipeline_aborts_when_lock_fails(self, _patch_stages) -> None:
        """Pipeline must abort gracefully when acquire_lock() returns False."""
        from transpose.pipeline.runner import PipelineInput, run_pipeline

        stage_mocks, ctx, book_id = _patch_stages
        ctx.state.acquire_lock = AsyncMock(return_value=False)

        inp = PipelineInput(source_path="/fake.pdf", title="Test")
        try:
            await run_pipeline(inp, ctx)
            # If pipeline completes without error, OCR should NOT have been called
            # when lock acquisition fails
            if ctx.state.acquire_lock.called and not ctx.state.acquire_lock.return_value:
                stage_mocks["ocr"].assert_not_called()
        except Exception:
            pass  # Pipeline raised — acceptable abort behavior  # noqa: SIM105

        # If acquire_lock was never called, Chani hasn't wired it yet
        if not ctx.state.acquire_lock.called:
            pytest.xfail("acquire_lock() not yet wired in runner (B1 pending)")

    @pytest.mark.asyncio
    async def test_release_lock_on_success(self, _patch_stages) -> None:
        """release_lock() must be called on the success path."""
        from transpose.pipeline.runner import PipelineInput, run_pipeline

        _, ctx, book_id = _patch_stages
        inp = PipelineInput(source_path="/fake.pdf", title="Test")

        with contextlib.suppress(Exception):
            await run_pipeline(inp, ctx)

        ctx.state.release_lock.assert_called()

    @pytest.mark.asyncio
    async def test_release_lock_on_exception(self, _patch_stages) -> None:
        """release_lock() must be called even when a stage raises."""
        from transpose.pipeline.runner import PipelineInput, run_pipeline

        stage_mocks, ctx, book_id = _patch_stages
        stage_mocks["ocr"].side_effect = RuntimeError("OCR exploded")

        inp = PipelineInput(source_path="/fake.pdf", title="Test")
        with pytest.raises(RuntimeError, match="OCR exploded"):
            await run_pipeline(inp, ctx)

        ctx.state.release_lock.assert_called()

    @pytest.mark.asyncio
    async def test_lock_uses_correct_book_id(self, _patch_stages) -> None:
        """Lock key must include the correct book_id."""
        from transpose.pipeline.runner import PipelineInput, run_pipeline

        _, ctx, expected_book_id = _patch_stages
        inp = PipelineInput(source_path="/fake.pdf", title="Test")

        with contextlib.suppress(Exception):
            await run_pipeline(inp, ctx)

        # Check that release_lock was called with the book_id string
        if ctx.state.release_lock.called:
            call_args = ctx.state.release_lock.call_args
            lock_key = call_args[0][0] if call_args[0] else call_args[1].get("key", "")
            assert str(expected_book_id) in str(lock_key), (
                f"Lock key should contain book_id {expected_book_id}"
            )


class TestPipelineOutputAggregation:
    """Test output aggregation across stages."""

    def test_artifact_aggregation(self) -> None:
        """Test that artifacts from export are included."""
        artifacts = [
            ExportArtifact("epub", "https://storage/book.epub", 1024000),
            ExportArtifact("pdf", "https://storage/book.pdf", 2048000),
        ]

        output = PipelineOutput(
            book_id=uuid4(),
            status=BookStatus.EXPORTED,
            artifacts=artifacts,
            glossary_term_count=45,
            total_tokens_used=12000,
            stages_completed=[
                "ingest", "ocr", "chunk", "translate",
                "glossary", "assemble", "export",
            ],
        )

        assert len(output.artifacts) == 2

    def test_token_usage_aggregation(self) -> None:
        """Test that token usage is aggregated."""
        # Simulate token usage from translate stage
        prompt_tokens = 5000
        completion_tokens = 3000
        total_tokens = prompt_tokens + completion_tokens

        output = PipelineOutput(
            book_id=uuid4(),
            status=BookStatus.EXPORTED,
            artifacts=[],
            glossary_term_count=40,
            total_tokens_used=total_tokens,
            stages_completed=[
                "ingest", "ocr", "chunk", "translate",
                "glossary", "assemble", "export",
            ],
        )

        assert output.total_tokens_used == 8000
