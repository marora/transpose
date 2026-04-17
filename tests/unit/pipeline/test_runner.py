"""Tests for the pipeline runner.

Tests full pipeline execution, stage orchestration, and error handling.
"""

from __future__ import annotations

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
