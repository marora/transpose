"""Stage 3: Chunk — Semantic text chunking for translation."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from transpose.models.enums import SectionType


@dataclass
class ChunkInput:
    book_id: UUID
    target_chunk_tokens: int = 1500
    overlap_tokens: int = 150


@dataclass
class ChunkResult:
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
    book_id: UUID
    total_chunks: int
    chunks: list[ChunkResult] = field(default_factory=list)


async def run(input: ChunkInput, ctx) -> ChunkOutput:  # type: ignore[no-untyped-def]
    """Split OCR'd pages into translation-ready chunks.

    Respects semantic boundaries (paragraphs, chapters, verses).
    Uses tiktoken for accurate token counting.
    """
    import logging
    import re

    import tiktoken

    from transpose.models.enums import BookStatus
    from transpose.models.translation import Chunk

    logger = logging.getLogger(__name__)

    # Get all pages for the book
    pages = await ctx.db.get_pages_for_book(input.book_id)
    if not pages:
        raise ValueError(f"No pages found for book: {input.book_id}")

    logger.info(f"Chunking {len(pages)} pages")

    # Merge pages into continuous text, joining paragraphs split across page boundaries
    full_text, page_boundaries = _join_cross_page_paragraphs(pages)

    # Initialize tokenizer
    encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding

    # Detect structural markers
    chapter_pattern = re.compile(r"^(Chapter|अध्याय|ਅਧਿਆਇ)\s+(\d+|[IVX]+)", re.MULTILINE)

    # Split on structural boundaries
    chunks: list[Chunk] = []
    sequence = 0

    # Split on double newlines (paragraphs) first
    paragraphs = full_text.split("\n\n")

    current_chunk_text = ""
    current_chunk_tokens = 0
    current_chapter = None
    chunk_start_pos = 0

    for para in paragraphs:
        if not para.strip():
            continue

        # Check for chapter marker
        chapter_match = chapter_pattern.match(para)
        if chapter_match:
            # Save current chunk if exists
            if current_chunk_text:
                chunks.append(
                    _create_chunk(
                        book_id=input.book_id,
                        sequence=sequence,
                        text=current_chunk_text.strip(),
                        encoding=encoding,
                        page_boundaries=page_boundaries,
                        chunk_start_pos=chunk_start_pos,
                        current_chapter=current_chapter,
                    )
                )
                sequence += 1

            current_chapter = para.strip()
            current_chunk_text = para + "\n\n"
            current_chunk_tokens = len(encoding.encode(para))
            chunk_start_pos = full_text.find(para)
            continue

        # Add paragraph to current chunk
        para_tokens = len(encoding.encode(para))

        if current_chunk_tokens + para_tokens > input.target_chunk_tokens and current_chunk_text:
            # Save current chunk
            chunks.append(
                _create_chunk(
                    book_id=input.book_id,
                    sequence=sequence,
                    text=current_chunk_text.strip(),
                    encoding=encoding,
                    page_boundaries=page_boundaries,
                    chunk_start_pos=chunk_start_pos,
                    current_chapter=current_chapter,
                )
            )
            sequence += 1

            # Start new chunk with overlap
            overlap_text = _get_overlap_text(
                current_chunk_text, input.overlap_tokens, encoding
            )
            current_chunk_text = overlap_text + para + "\n\n"
            current_chunk_tokens = len(encoding.encode(current_chunk_text))
            chunk_start_pos = full_text.find(para)
        else:
            current_chunk_text += para + "\n\n"
            current_chunk_tokens += para_tokens

    # Save final chunk
    if current_chunk_text.strip():
        chunks.append(
            _create_chunk(
                book_id=input.book_id,
                sequence=sequence,
                text=current_chunk_text.strip(),
                encoding=encoding,
                page_boundaries=page_boundaries,
                chunk_start_pos=chunk_start_pos,
                current_chapter=current_chapter,
            )
        )

    # Delete existing chunks (re-chunking replaces)
    await ctx.db.delete_chunks_for_book(input.book_id)

    # Save new chunks
    await ctx.db.create_chunks(chunks)
    logger.info(f"Created {len(chunks)} chunks")

    # Update book status
    await ctx.db.update_book_status(input.book_id, BookStatus.CHUNKED)

    # Build output
    chunk_results = [
        ChunkResult(
            chunk_id=chunk.id,
            sequence=chunk.sequence,
            source_text=chunk.source_text,
            token_count=chunk.token_count,
            chapter_ref=chunk.chapter_ref,
            section_type=chunk.section_type,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )
        for chunk in chunks
    ]

    return ChunkOutput(
        book_id=input.book_id,
        total_chunks=len(chunks),
        chunks=chunk_results,
    )


def _ends_with_terminal(text: str) -> bool:
    """Check if text ends with sentence-terminal punctuation."""
    terminal_chars = {'.', '?', '!', '।', '॥', '—', '"', "'", '\u201d', '\u2019'}
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in terminal_chars


def _starts_with_continuation(text: str) -> bool:
    """Check if text starts with a continuation pattern (lowercase, Devanagari, etc.)."""
    stripped = text.lstrip()
    if not stripped:
        return False
    first_char = stripped[0]
    # Lowercase Latin letter = likely mid-sentence continuation
    if first_char.islower():
        return True
    # Devanagari characters (U+0900–U+097F) — Hindi text rarely starts a new
    # sentence with an explicit marker, so Devanagari after a non-terminal ending
    # is very likely a continuation.
    return '\u0900' <= first_char <= '\u097F'


def _join_cross_page_paragraphs(pages) -> tuple[str, list[tuple[int, int]]]:
    """Merge pages into continuous text, joining paragraphs that span page boundaries.

    When a page ends without terminal punctuation and the next page begins
    with a continuation pattern (lowercase letter, Devanagari script), the
    artificial ``\\n\\n`` page break is replaced with a single space so the
    downstream paragraph splitter keeps the sentence intact.
    """
    import logging

    logger = logging.getLogger(__name__)

    full_text = ""
    page_boundaries: list[tuple[int, int]] = []

    for i, page in enumerate(pages):
        text = page.raw_text

        if i > 0 and full_text:
            prev_end = full_text.rstrip()
            curr_start = text.lstrip()
            if (
                prev_end
                and curr_start
                and not _ends_with_terminal(prev_end)
                and _starts_with_continuation(curr_start)
            ):
                # Replace the trailing \n\n with a single space to join
                full_text = full_text.rstrip() + " "
                logger.debug(
                    "Joined paragraph across page boundary %d→%d",
                    pages[i - 1].page_number,
                    page.page_number,
                )
                start_pos = len(full_text)
                page_boundaries.append((start_pos, page.page_number))
                full_text += text + "\n\n"
                continue

        start_pos = len(full_text)
        page_boundaries.append((start_pos, page.page_number))
        full_text += text + "\n\n"

    return full_text, page_boundaries


def _create_chunk(
    book_id,
    sequence: int,
    text: str,
    encoding,
    page_boundaries: list[tuple[int, int]],
    chunk_start_pos: int,
    current_chapter: str | None,
):
    """Create a chunk object."""
    from transpose.models.enums import SectionType
    from transpose.models.translation import Chunk

    token_count = len(encoding.encode(text))

    # Determine page range
    page_start = 1
    page_end = 1
    for pos, page_num in page_boundaries:
        if pos <= chunk_start_pos:
            page_start = page_num
            page_end = page_num

    # Detect section type
    section_type = SectionType.PROSE
    if current_chapter and (
        "Chapter" in current_chapter
        or "अध्याय" in current_chapter
        or "ਅਧਿਆਇ" in current_chapter
    ):
        section_type = SectionType.CHAPTER

    return Chunk(
        book_id=book_id,
        sequence=sequence,
        source_text=text,
        token_count=token_count,
        page_start=page_start,
        page_end=page_end,
        section_type=section_type,
        chapter_ref=current_chapter,
    )


def _get_overlap_text(text: str, overlap_tokens: int, encoding) -> str:
    """Get the last N tokens of text for overlap."""
    tokens = encoding.encode(text)
    if len(tokens) <= overlap_tokens:
        return text

    overlap_tokens_list = tokens[-overlap_tokens:]
    return encoding.decode(overlap_tokens_list) + "\n\n"

