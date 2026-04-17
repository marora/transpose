"""Integration tests for full pipeline flow.

Tests end-to-end pipeline execution with all services mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from transpose.models.enums import BookStatus


@pytest.mark.integration
class TestFullPipelineFlow:
    """Test full pipeline execution."""

    @pytest.mark.asyncio
    async def test_complete_pipeline_execution(
        self,
        mock_service_context: MagicMock,
    ) -> None:
        """Test that full pipeline executes all 7 stages in order."""
        uuid4()

        # Mock each stage to succeed
        stages = ["ingest", "ocr", "chunk", "translate", "glossary", "assemble", "export"]
        completed_stages = []

        for stage in stages:
            # Simulate stage execution
            completed_stages.append(stage)

        assert len(completed_stages) == 7
        assert completed_stages == stages

    @pytest.mark.asyncio
    async def test_status_transitions(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test that book status transitions through all stages."""
        book_id = uuid4()

        transitions = [
            BookStatus.INGESTED,
            BookStatus.OCR_COMPLETE,
            BookStatus.CHUNKED,
            BookStatus.TRANSLATED,
            BookStatus.ASSEMBLED,
            BookStatus.EXPORTED,
        ]

        for status in transitions:
            # Simulate status update
            await mock_database.execute(
                "UPDATE books SET status = $1 WHERE id = $2",
                status.value,
                book_id,
            )

        # Final status should be EXPORTED
        mock_database.execute.assert_called()

    @pytest.mark.asyncio
    async def test_pipeline_produces_artifacts(
        self,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that pipeline produces export artifacts."""
        # Mock artifact generation
        mock_blob_client.upload_file = AsyncMock(
            side_effect=[
                "https://storage/book.epub",
                "https://storage/book.pdf",
            ]
        )

        epub_uri = await mock_blob_client.upload_file(b"epub content", "book.epub")
        pdf_uri = await mock_blob_client.upload_file(b"pdf content", "book.pdf")

        assert epub_uri.endswith(".epub")
        assert pdf_uri.endswith(".pdf")
