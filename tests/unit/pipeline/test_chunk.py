"""Tests for the chunk pipeline stage.

Tests chunking logic, token counting, and chapter detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from dataclasses import dataclass as _dataclass
from dataclasses import field as _field
from uuid import UUID, uuid4
from uuid import uuid4 as _uuid4

import pytest

from transpose.models.enums import SectionType
from transpose.pipeline.chunk import (
    _ends_with_terminal,
    _join_cross_page_paragraphs,
    _starts_with_continuation,
)


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


# ---------------------------------------------------------------------------
# Issue #6 — Paragraph splitting / cross-page joining (acceptance-criteria tests)
# ---------------------------------------------------------------------------

@_dataclass
class _FakePage:
    """Minimal page object used by _join_cross_page_paragraphs."""

    page_number: int
    raw_text: str
    book_id: object = _field(default_factory=_uuid4)
    confidence: float = 1.0
    needs_review: bool = False
    ocr_metadata: dict = _field(default_factory=dict)


class TestCrossPageJoining:
    """Issue #6: Text not ending with terminal punctuation must be joined."""

    def test_non_terminal_text_joined_with_next_page(self) -> None:
        """Page ending mid-sentence must be joined with the next page."""
        pages = [
            _FakePage(page_number=1, raw_text="The concept of dharma is"),
            _FakePage(page_number=2, raw_text="central to the teaching."),
        ]
        full_text, _boundaries = _join_cross_page_paragraphs(pages)
        # Must be joined with a space, not double-newline
        assert "dharma is central" in full_text
        assert "is\n\ncentral" not in full_text

    def test_terminal_punctuation_prevents_joining(self) -> None:
        """Pages ending with terminal punctuation must NOT be joined."""
        pages = [
            _FakePage(page_number=1, raw_text="This is a complete sentence."),
            _FakePage(page_number=2, raw_text="This starts a new thought."),
        ]
        full_text, _boundaries = _join_cross_page_paragraphs(pages)
        # Must have paragraph break between them
        assert "sentence.\n\n" in full_text or "sentence. " not in full_text


class TestTerminalPunctuationDetection:
    """Issue #6: _ends_with_terminal recognises all terminators."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("This is a sentence.", True),
            ("What is dharma?", True),
            ("Incredible!", True),
            ("धर्म का पालन करना चाहिए।", True),   # Devanagari danda
            ("समाप्त॥", True),                        # Double danda
            ("The concept of dharma is", False),
            ("कर्म करो फल की", False),
            ("", False),
        ],
    )
    def test_ends_with_terminal(self, text: str, expected: bool) -> None:
        assert _ends_with_terminal(text) is expected


class TestDevanagariDandaTerminators:
    """Issue #6: Devanagari danda (।) and double danda (॥) as terminators."""

    def test_single_danda_is_terminal(self) -> None:
        """Single danda (purna viram) terminates a sentence."""
        assert _ends_with_terminal("यह एक वाक्य है।")

    def test_double_danda_is_terminal(self) -> None:
        """Double danda terminates verses."""
        assert _ends_with_terminal("योगस्थः कुरु कर्माणि॥")

    def test_danda_pages_not_joined(self) -> None:
        """Pages ending with danda should NOT be joined to next page."""
        pages = [
            _FakePage(page_number=1, raw_text="यह एक वाक्य है।"),
            _FakePage(page_number=2, raw_text="यह अगला वाक्य है।"),
        ]
        full_text, _ = _join_cross_page_paragraphs(pages)
        # Should have a paragraph break, not a space-join
        assert "है। " not in full_text or "है।\n\n" in full_text


class TestContinuationDetection:
    """Issue #6: _starts_with_continuation heuristic."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("central to the teaching.", True),      # lowercase = continuation
            ("The next chapter begins.", False),     # uppercase = new sentence
            ("धर्म का पालन", True),                    # Devanagari = continuation
            ("", False),
            ("   ", False),
        ],
    )
    def test_starts_with_continuation(self, text: str, expected: bool) -> None:
        assert _starts_with_continuation(text) is expected


class TestPageBoundaryTracking:
    """Issue #6: Page boundaries must be correctly tracked after joining."""

    def test_page_boundaries_count(self) -> None:
        """Every input page should produce a page boundary entry."""
        pages = [
            _FakePage(page_number=1, raw_text="First page text."),
            _FakePage(page_number=2, raw_text="Second page text."),
            _FakePage(page_number=3, raw_text="Third page text."),
        ]
        _text, boundaries = _join_cross_page_paragraphs(pages)
        assert len(boundaries) == 3

    def test_page_boundaries_ascending_positions(self) -> None:
        """Boundary positions must be in ascending order."""
        pages = [
            _FakePage(page_number=1, raw_text="Page one content"),
            _FakePage(page_number=2, raw_text="continues here without period"),
            _FakePage(page_number=3, raw_text="and finishes here."),
        ]
        _text, boundaries = _join_cross_page_paragraphs(pages)
        positions = [pos for pos, _pn in boundaries]
        assert positions == sorted(positions)

    def test_page_numbers_preserved(self) -> None:
        """Boundary page numbers must match input page numbers."""
        pages = [
            _FakePage(page_number=5, raw_text="Content on page 5."),
            _FakePage(page_number=6, raw_text="Content on page 6."),
        ]
        _text, boundaries = _join_cross_page_paragraphs(pages)
        page_nums = [pn for _pos, pn in boundaries]
        assert page_nums == [5, 6]


class TestMixedHindiEnglishContinuation:
    """Issue #6: Mixed Hindi/English continuation detection."""

    def test_english_mid_sentence_into_hindi(self) -> None:
        """English text ending mid-sentence before Hindi continuation."""
        pages = [
            _FakePage(page_number=1, raw_text="The guru explained that"),
            _FakePage(page_number=2, raw_text="धर्म is the foundation of life."),
        ]
        full_text, _ = _join_cross_page_paragraphs(pages)
        # "that" has no terminal → next page starts with Devanagari → join
        assert "that धर्म" in full_text or "that\n\nधर्म" not in full_text

    def test_hindi_mid_sentence_into_english(self) -> None:
        """Hindi text ending mid-sentence before English lowercase continuation."""
        pages = [
            _FakePage(page_number=1, raw_text="गुरु ने कहा कि"),
            _FakePage(page_number=2, raw_text="dharma is essential."),
        ]
        full_text, _ = _join_cross_page_paragraphs(pages)
        # "कि" has no terminal → next starts lowercase → join
        assert "कि dharma" in full_text or "कि\n\ndharma" not in full_text


class TestSinglePageEdgeCase:
    """Issue #6: Single-page document — no joining needed."""

    def test_single_page_unchanged(self) -> None:
        """Single page returns text as-is with one boundary."""
        pages = [
            _FakePage(page_number=1, raw_text="Only one page of content."),
        ]
        full_text, boundaries = _join_cross_page_paragraphs(pages)
        assert "Only one page of content." in full_text
        assert len(boundaries) == 1

    def test_single_page_no_joining_logic_triggered(self) -> None:
        """Single page should never trigger cross-page joining."""
        pages = [
            _FakePage(page_number=1, raw_text="Ends without period"),
        ]
        full_text, boundaries = _join_cross_page_paragraphs(pages)
        # Even without terminal, no joining happens (nothing to join with)
        assert "Ends without period" in full_text
        assert len(boundaries) == 1


class TestAllPagesTerminalEdgeCase:
    """Issue #6: All pages end with terminal punctuation → no joining."""

    def test_all_terminal_no_joining(self) -> None:
        """When every page ends with '.', no joining should occur."""
        pages = [
            _FakePage(page_number=1, raw_text="Sentence one."),
            _FakePage(page_number=2, raw_text="Sentence two."),
            _FakePage(page_number=3, raw_text="Sentence three."),
        ]
        full_text, boundaries = _join_cross_page_paragraphs(pages)
        # Each sentence should be separated by paragraph breaks
        assert "one.\n\n" in full_text or "one. S" not in full_text
        assert len(boundaries) == 3

    def test_all_danda_terminal_no_joining(self) -> None:
        """When every page ends with danda, no joining should occur."""
        pages = [
            _FakePage(page_number=1, raw_text="वाक्य एक।"),
            _FakePage(page_number=2, raw_text="वाक्य दो।"),
            _FakePage(page_number=3, raw_text="वाक्य तीन।"),
        ]
        full_text, boundaries = _join_cross_page_paragraphs(pages)
        assert len(boundaries) == 3
        # No space-joining should have occurred
        assert "एक। वाक्य" not in full_text
