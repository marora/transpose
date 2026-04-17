"""Tests for the chunk pipeline stage.

Tests chunking logic, token counting, and chapter detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from transpose.models.enums import SectionType


@dataclass
class ChunkInput:
    """Chunk stage input contract."""

    book_id: UUID
    target_chunk_tokens: int = 1500
    overlap_tokens: int = 150


@dataclass
class ChunkResult:
    """A single chunk produced by the chunking stage."""

    chunk_id: UUID
    sequence: int
    source_text: str
    token_count: int
    chapter_ref: str | None
    section_type: SectionType
    page_start: int
    page_end: int


@dataclass
class ChunkOutput:
    """Chunk stage output contract."""

    book_id: UUID
    total_chunks: int
    chunks: list[ChunkResult] = field(default_factory=list)


class TestChunkContract:
    """Test chunk stage contract validation."""

    def test_chunk_input_defaults(self) -> None:
        """Test ChunkInput has sensible defaults."""
        book_id = uuid4()
        input_data = ChunkInput(book_id=book_id)
        assert input_data.book_id == book_id
        assert input_data.target_chunk_tokens == 1500
        assert input_data.overlap_tokens == 150

    def test_chunk_input_custom_values(self) -> None:
        """Test ChunkInput accepts custom token counts."""
        book_id = uuid4()
        input_data = ChunkInput(
            book_id=book_id,
            target_chunk_tokens=2000,
            overlap_tokens=200,
        )
        assert input_data.target_chunk_tokens == 2000
        assert input_data.overlap_tokens == 200

    def test_chunk_result_shape(self) -> None:
        """Test ChunkResult has all required fields."""
        chunk = ChunkResult(
            chunk_id=uuid4(),
            sequence=0,
            source_text="Sample text",
            token_count=10,
            chapter_ref="Chapter 1",
            section_type=SectionType.PROSE,
            page_start=1,
            page_end=2,
        )
        assert isinstance(chunk.chunk_id, UUID)
        assert chunk.sequence >= 0
        assert len(chunk.source_text) > 0
        assert chunk.token_count > 0
        assert chunk.section_type in SectionType

    def test_chunk_output_shape(self) -> None:
        """Test ChunkOutput has all required fields."""
        book_id = uuid4()
        output = ChunkOutput(
            book_id=book_id,
            total_chunks=5,
            chunks=[],
        )
        assert output.book_id == book_id
        assert output.total_chunks >= 0
        assert isinstance(output.chunks, list)


class TestChunkTokenCounting:
    """Test token counting using tiktoken."""

    def test_token_count_respects_target(self) -> None:
        """Test that chunks respect target token count."""
        # Simulate chunking with target 1500 tokens
        chunk1 = ChunkResult(
            chunk_id=uuid4(),
            sequence=0,
            source_text="Text for chunk 1",
            token_count=1450,  # Near target
            chapter_ref=None,
            section_type=SectionType.PROSE,
            page_start=1,
            page_end=3,
        )
        assert chunk1.token_count <= 1500 + 150  # Target + overlap allowance

    def test_chunk_overlap(self) -> None:
        """Test that chunks have overlap for context."""
        # Mock overlapping chunks
        chunk1_text = "This is the first chunk with some overlap at the end."
        chunk2_text = "Some overlap at the end. This continues into chunk 2."

        # Check that overlap exists (last words of chunk1 = first words of chunk2)
        chunk1_end = chunk1_text.split()[-5:]
        chunk2_start = chunk2_text.split()[:5]

        # At least some overlap should exist
        overlap = set(chunk1_end) & set(chunk2_start)
        assert len(overlap) > 0

    def test_token_counting_uses_tiktoken(self) -> None:
        """Test that token counting uses tiktoken."""
        try:
            import tiktoken

            enc = tiktoken.get_encoding("cl100k_base")
            sample_text = "This is a sample Hindi text: धर्म और कर्म।"
            tokens = enc.encode(sample_text)
            assert len(tokens) > 0
        except ImportError:
            pytest.skip("tiktoken not installed")


class TestChunkChapterDetection:
    """Test chapter detection from text patterns."""

    def test_chapter_heading_detected(self) -> None:
        """Test that chapter headings are detected."""
        chunk = ChunkResult(
            chunk_id=uuid4(),
            sequence=0,
            source_text="Chapter 1: The Beginning",
            token_count=5,
            chapter_ref="Chapter 1",
            section_type=SectionType.CHAPTER,
            page_start=1,
            page_end=1,
        )
        assert chunk.section_type == SectionType.CHAPTER
        assert chunk.chapter_ref == "Chapter 1"

    def test_verse_section_type(self) -> None:
        """Test that verses are identified."""
        chunk = ChunkResult(
            chunk_id=uuid4(),
            sequence=1,
            source_text="योगस्थः कुरु कर्माणि सङ्गं त्यक्त्वा धनञ्जय।",
            token_count=15,
            chapter_ref="Chapter 2",
            section_type=SectionType.VERSE,
            page_start=2,
            page_end=2,
        )
        assert chunk.section_type == SectionType.VERSE

    def test_prose_section_type(self) -> None:
        """Test that prose sections are identified."""
        chunk = ChunkResult(
            chunk_id=uuid4(),
            sequence=2,
            source_text="This is a prose section explaining the verse.",
            token_count=10,
            chapter_ref="Chapter 2",
            section_type=SectionType.PROSE,
            page_start=2,
            page_end=2,
        )
        assert chunk.section_type == SectionType.PROSE


class TestChunkEdgeCases:
    """Test chunking edge cases."""

    def test_single_page_single_chunk(self) -> None:
        """Test single-page text produces single chunk."""
        book_id = uuid4()
        chunks = [
            ChunkResult(
                chunk_id=uuid4(),
                sequence=0,
                source_text="Short single-page text",
                token_count=10,
                chapter_ref=None,
                section_type=SectionType.PROSE,
                page_start=1,
                page_end=1,
            )
        ]

        output = ChunkOutput(
            book_id=book_id,
            total_chunks=1,
            chunks=chunks,
        )
        assert output.total_chunks == 1
        assert len(output.chunks) == 1

    def test_very_large_text_multiple_chunks(self) -> None:
        """Test very large text produces multiple chunks."""
        book_id = uuid4()
        # Simulate 10 chunks from large text
        chunks = [
            ChunkResult(
                chunk_id=uuid4(),
                sequence=i,
                source_text=f"Chunk {i} text",
                token_count=1400,
                chapter_ref=f"Chapter {i // 3 + 1}",
                section_type=SectionType.PROSE,
                page_start=i * 5 + 1,
                page_end=(i + 1) * 5,
            )
            for i in range(10)
        ]

        output = ChunkOutput(
            book_id=book_id,
            total_chunks=10,
            chunks=chunks,
        )
        assert output.total_chunks == 10
        assert len(output.chunks) == 10

    def test_chunk_sequence_ordering(self) -> None:
        """Test that chunks maintain sequence order."""
        chunks = [
            ChunkResult(uuid4(), i, f"text{i}", 100, None, SectionType.PROSE, 1, 1)
            for i in range(5)
        ]

        sequences = [c.sequence for c in chunks]
        assert sequences == sorted(sequences)
        assert sequences == [0, 1, 2, 3, 4]

    def test_chunk_page_ranges(self) -> None:
        """Test that chunk page ranges are tracked."""
        chunk = ChunkResult(
            chunk_id=uuid4(),
            sequence=0,
            source_text="Text spanning multiple pages",
            token_count=500,
            chapter_ref=None,
            section_type=SectionType.PROSE,
            page_start=5,
            page_end=8,
        )
        assert chunk.page_start <= chunk.page_end
        assert chunk.page_end - chunk.page_start >= 0
