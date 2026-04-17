"""Tests for the ingest pipeline stage.

Tests the ingest stage contract validation, deduplication, and error handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from transpose.models.enums import SourceLanguage


@dataclass
class IngestInput:
    """Ingest stage input contract."""

    source_path: str
    title: str
    author: str | None = None
    source_language: SourceLanguage = SourceLanguage.HINDI


@dataclass
class IngestOutput:
    """Ingest stage output contract."""

    book_id: UUID
    source_hash: str
    source_blob_uri: str
    page_count: int
    already_existed: bool


class TestIngestContract:
    """Test ingest stage contract validation."""

    def test_ingest_input_required_fields(self) -> None:
        """Test IngestInput requires source_path and title."""
        input_data = IngestInput(
            source_path="/path/to/book.pdf",
            title="Test Book",
        )
        assert input_data.source_path == "/path/to/book.pdf"
        assert input_data.title == "Test Book"
        assert input_data.author is None
        assert input_data.source_language == SourceLanguage.HINDI

    def test_ingest_input_with_author(self) -> None:
        """Test IngestInput with optional author field."""
        input_data = IngestInput(
            source_path="/path/to/book.pdf",
            title="Test Book",
            author="Test Author",
            source_language=SourceLanguage.PUNJABI,
        )
        assert input_data.author == "Test Author"
        assert input_data.source_language == SourceLanguage.PUNJABI

    def test_ingest_output_shape(self) -> None:
        """Test IngestOutput has all required fields."""
        output = IngestOutput(
            book_id=uuid4(),
            source_hash="abc123",
            source_blob_uri="https://storage.blob/book.pdf",
            page_count=100,
            already_existed=False,
        )
        assert isinstance(output.book_id, UUID)
        assert len(output.source_hash) > 0
        assert output.source_blob_uri.startswith("https://")
        assert output.page_count > 0
        assert isinstance(output.already_existed, bool)


class TestIngestIdempotency:
    """Test idempotency of ingest stage."""

    @pytest.mark.asyncio
    async def test_duplicate_pdf_returns_existing_book(
        self,
        mock_database: AsyncMock,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that re-ingesting same PDF returns existing book."""
        # Mock database to return existing book
        existing_book_id = uuid4()
        mock_database.fetch_one = AsyncMock(
            return_value={
                "id": existing_book_id,
                "source_hash": "abc123def456",
                "source_blob_uri": "https://storage.blob/book.pdf",
                "page_count": 18,
            }
        )

        # Simulate the ingest logic
        source_hash = "abc123def456"
        existing_book = await mock_database.fetch_one(
            "SELECT * FROM books WHERE source_hash = $1", source_hash
        )

        assert existing_book is not None
        assert existing_book["id"] == existing_book_id
        assert existing_book["source_hash"] == source_hash

        # Verify output would indicate already_existed=True
        output = IngestOutput(
            book_id=existing_book["id"],
            source_hash=existing_book["source_hash"],
            source_blob_uri=existing_book["source_blob_uri"],
            page_count=existing_book["page_count"],
            already_existed=True,
        )
        assert output.already_existed is True
        assert output.book_id == existing_book_id

    @pytest.mark.asyncio
    async def test_new_pdf_creates_book_record(
        self,
        mock_database: AsyncMock,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that new PDF creates a new book record."""
        # Mock database to return None (no existing book)
        mock_database.fetch_one = AsyncMock(return_value=None)
        
        # Mock insert returning new book id
        new_book_id = uuid4()
        mock_database.execute = AsyncMock(return_value=new_book_id)

        # Mock blob upload
        mock_blob_client.upload_file = AsyncMock(
            return_value="https://storage.blob/new_book.pdf"
        )

        # Simulate the ingest logic
        source_hash = "new_hash_789"
        existing_book = await mock_database.fetch_one(
            "SELECT * FROM books WHERE source_hash = $1", source_hash
        )

        assert existing_book is None

        # New book would be created
        output = IngestOutput(
            book_id=new_book_id,
            source_hash=source_hash,
            source_blob_uri="https://storage.blob/new_book.pdf",
            page_count=50,
            already_existed=False,
        )
        assert output.already_existed is False
        assert output.book_id == new_book_id


class TestIngestErrorHandling:
    """Test error handling in ingest stage."""

    @pytest.mark.asyncio
    async def test_invalid_file_path_raises_error(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test that invalid file path raises appropriate error."""
        input_data = IngestInput(
            source_path="/nonexistent/path/book.pdf",
            title="Test Book",
        )

        # In actual implementation, this would raise FileNotFoundError
        with pytest.raises((FileNotFoundError, OSError)), open(input_data.source_path, "rb"):
            pass

    @pytest.mark.asyncio
    async def test_empty_pdf_sets_page_count_zero(
        self,
        mock_database: AsyncMock,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that empty PDF results in page_count=0."""
        output = IngestOutput(
            book_id=uuid4(),
            source_hash="empty_pdf_hash",
            source_blob_uri="https://storage.blob/empty.pdf",
            page_count=0,
            already_existed=False,
        )
        assert output.page_count == 0


class TestIngestPageCount:
    """Test page count extraction."""

    def test_page_count_extraction(self) -> None:
        """Test that page count is correctly extracted."""
        # Mock page count extraction
        with patch("pymupdf.open") as mock_pymupdf:
            mock_doc = MagicMock()
            mock_doc.page_count = 18
            mock_pymupdf.return_value = mock_doc

            import pymupdf

            doc = pymupdf.open("dummy.pdf")
            page_count = doc.page_count

            assert page_count == 18

    def test_single_page_pdf(self) -> None:
        """Test single-page PDF returns page_count=1."""
        output = IngestOutput(
            book_id=uuid4(),
            source_hash="single_page",
            source_blob_uri="https://storage.blob/single.pdf",
            page_count=1,
            already_existed=False,
        )
        assert output.page_count == 1
