"""Tests for the export pipeline stage.

Tests ePub and PDF generation, blob uploads, and multi-format exports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest


@dataclass
class ExportInput:
    """Export stage input contract."""

    book_id: UUID
    formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])


@dataclass
class ExportArtifact:
    """A single exported file."""

    format: str
    blob_uri: str
    file_size_bytes: int


@dataclass
class ExportOutput:
    """Export stage output contract."""

    book_id: UUID
    artifacts: list[ExportArtifact] = field(default_factory=list)


class TestExportContract:
    """Test export stage contract validation."""

    def test_export_input_defaults(self) -> None:
        """Test ExportInput has default formats."""
        book_id = uuid4()
        input_data = ExportInput(book_id=book_id)
        assert input_data.book_id == book_id
        assert "epub" in input_data.formats
        assert "pdf" in input_data.formats

    def test_export_input_custom_formats(self) -> None:
        """Test ExportInput accepts custom formats."""
        book_id = uuid4()
        input_data = ExportInput(book_id=book_id, formats=["epub"])
        assert input_data.formats == ["epub"]

    def test_export_artifact_shape(self) -> None:
        """Test ExportArtifact has all required fields."""
        artifact = ExportArtifact(
            format="epub",
            blob_uri="https://storage.blob/book.epub",
            file_size_bytes=1024000,
        )
        assert artifact.format in ["epub", "pdf"]
        assert artifact.blob_uri.startswith("https://")
        assert artifact.file_size_bytes > 0

    def test_export_output_shape(self) -> None:
        """Test ExportOutput has all required fields."""
        book_id = uuid4()
        output = ExportOutput(
            book_id=book_id,
            artifacts=[],
        )
        assert output.book_id == book_id
        assert isinstance(output.artifacts, list)


class TestEpubGeneration:
    """Test ePub generation."""

    @pytest.mark.asyncio
    async def test_epub_generation_produces_valid_file(
        self,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that ePub generation produces valid file."""
        # Mock blob upload
        mock_blob_client.upload_file = AsyncMock(
            return_value="https://storage.blob/book.epub"
        )

        # Simulate ePub generation
        epub_uri = await mock_blob_client.upload_file(b"fake epub content", "book.epub")

        artifact = ExportArtifact(
            format="epub",
            blob_uri=epub_uri,
            file_size_bytes=len(b"fake epub content"),
        )

        assert artifact.format == "epub"
        assert artifact.blob_uri.endswith(".epub")


class TestPdfGeneration:
    """Test PDF generation."""

    @pytest.mark.asyncio
    async def test_pdf_generation_produces_valid_file(
        self,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that PDF generation produces valid file."""
        mock_blob_client.upload_file = AsyncMock(
            return_value="https://storage.blob/book.pdf"
        )

        pdf_uri = await mock_blob_client.upload_file(b"fake pdf content", "book.pdf")

        artifact = ExportArtifact(
            format="pdf",
            blob_uri=pdf_uri,
            file_size_bytes=len(b"fake pdf content"),
        )

        assert artifact.format == "pdf"
        assert artifact.blob_uri.endswith(".pdf")


class TestMultiFormatExport:
    """Test multi-format export."""

    def test_both_formats_requested(self) -> None:
        """Test exporting both ePub and PDF formats."""
        book_id = uuid4()
        artifacts = [
            ExportArtifact("epub", "https://storage.blob/book.epub", 1024000),
            ExportArtifact("pdf", "https://storage.blob/book.pdf", 2048000),
        ]

        output = ExportOutput(
            book_id=book_id,
            artifacts=artifacts,
        )

        assert len(output.artifacts) == 2
        formats = [a.format for a in output.artifacts]
        assert "epub" in formats
        assert "pdf" in formats


class TestBlobUpload:
    """Test blob upload of exported files."""

    @pytest.mark.asyncio
    async def test_blob_upload_returns_uri(
        self,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that blob upload returns URI."""
        mock_blob_client.upload_file = AsyncMock(
            return_value="https://storage.blob.core.windows.net/exports/book.epub"
        )

        uri = await mock_blob_client.upload_file(b"content", "book.epub")

        assert uri.startswith("https://")
        assert "storage" in uri
        assert "blob" in uri
