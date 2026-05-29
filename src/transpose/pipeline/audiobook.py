"""Stage 8: Audiobook — TTS generation with chapter-aware audio output.

Converts the translated manuscript into high-quality chapter-wise audio
using the configured TTS provider (default: Azure AI Speech Neural HD).

Implements: #126 — Core TTS pipeline stage.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from uuid import UUID

from transpose.services.tts_provider import AudioResult, SSMLOptions, WordBoundary

logger = logging.getLogger(__name__)

# Target max chapter duration ~25 min. At ~150 wpm narration and ~5 chars/word,
# that's ~18,750 words or ~112,500 chars. We split above this.
_MAX_CHAPTER_CHARS = 100_000
_MIN_CHAPTER_CHARS = 5_000  # Don't split tiny chapters


@dataclass
class AudiobookInput:
    book_id: UUID
    voice: str = ""  # Empty = use provider default
    formats: list[str] = field(default_factory=lambda: ["mp3"])


@dataclass
class ChapterAudio:
    chapter_number: int
    title: str
    blob_uri: str
    duration_ms: int
    file_size_bytes: int
    word_boundaries_uri: str = ""  # URI to JSON word boundaries (for read-along)


@dataclass
class AudiobookOutput:
    book_id: UUID
    chapters: list[ChapterAudio] = field(default_factory=list)
    total_duration_ms: int = 0
    total_cost: float = 0.0
    feed_uri: str = ""  # RSS feed URI (populated by feed generation stage)


def _strip_html(html: str) -> str:
    """Extract plain text from chapter HTML content."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode common entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&nbsp;", " ")
    text = text.replace("&#8217;", "\u2019")
    text = text.replace("&#8220;", "\u201c")
    text = text.replace("&#8221;", "\u201d")
    # Collapse whitespace but preserve paragraph breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_long_chapter(text: str, max_chars: int = _MAX_CHAPTER_CHARS) -> list[str]:
    """Split a long chapter into parts at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > max_chars and current:
            parts.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2  # +2 for \n\n

    if current:
        parts.append("\n\n".join(current))

    return parts


def _build_pronunciation_lexicon(glossary_terms: list[dict]) -> dict[str, str]:
    """Build pronunciation lexicon from glossary terms.

    Maps cultural terms to IPA pronunciations for consistent TTS rendering.
    Terms without explicit IPA get a best-effort transliteration hint.
    """
    lexicon: dict[str, str] = {}

    # Common cultural term pronunciations (Hindi/Punjabi religious terms)
    _KNOWN_PRONUNCIATIONS = {
        "atman": "\u0251\u02d0tm\u0259n",
        "dharma": "d\u02b0\u0251\u02d0rm\u0259",
        "karma": "k\u0251\u02d0rm\u0259",
        "seva": "se\u026av\u0251\u02d0",
        "sangat": "s\u0259\u014b\u0261\u0259t",
        "gurdwara": "\u0261\u028a\u0279dw\u0251\u02d0r\u0259",
        "langar": "l\u0259\u014b\u0261\u0259\u0279",
        "kirtan": "ki\u02d0rt\u0259n",
        "simran": "s\u026amr\u0259n",
        "waheguru": "w\u0251\u02d0he\u0261\u028aru\u02d0",
        "guru": "\u0261\u028aru\u02d0",
        "gurbani": "\u0261\u028arb\u0251\u02d0ni\u02d0",
        "naam": "n\u0251\u02d0m",
        "hukam": "h\u028ak\u0259m",
    }

    for entry in glossary_terms:
        term = entry.get("term", "").lower()
        if term in _KNOWN_PRONUNCIATIONS:
            lexicon[entry.get("term", "")] = _KNOWN_PRONUNCIATIONS[term]

    return lexicon


async def run(input: AudiobookInput, ctx) -> AudiobookOutput:
    """Generate audiobook from manuscript chapters.

    Fetches the manuscript, extracts text per chapter, synthesizes audio
    via the configured TTS provider, and uploads MP3 artifacts to blob storage.
    """
    from transpose.models.enums import BookStatus

    # Get book and manuscript
    book = await ctx.db.get_book(input.book_id)
    if not book:
        raise ValueError(f"Book not found: {input.book_id}")

    manuscript = await ctx.db.get_manuscript_for_book(input.book_id)
    if not manuscript:
        raise ValueError(f"No manuscript found for book: {input.book_id}")

    # Get glossary for pronunciation lexicon
    glossary = await ctx.db.get_glossary_for_book(input.book_id)
    glossary_terms = []
    if glossary and hasattr(glossary, "terms"):
        glossary_terms = glossary.terms if isinstance(glossary.terms, list) else []

    pronunciation_lexicon = _build_pronunciation_lexicon(glossary_terms)

    logger.info(
        f"Starting audiobook generation for: {book.title} "
        f"({len(manuscript.chapters)} chapters, "
        f"{len(pronunciation_lexicon)} pronunciation entries)"
    )

    # Configure TTS
    tts = ctx.tts
    voice = input.voice or ""
    ssml_options = SSMLOptions(
        rate="-10%",
        paragraph_pause_ms=500,
        chapter_intro_pause_ms=2000,
        pronunciation_lexicon=pronunciation_lexicon,
    )

    chapters_audio: list[ChapterAudio] = []
    total_cost = 0.0

    for chapter in manuscript.chapters:
        chapter_text = _strip_html(chapter.content_html)
        if not chapter_text.strip():
            logger.warning(f"Chapter {chapter.number} is empty, skipping")
            continue

        # Split long chapters into parts
        parts = _split_long_chapter(chapter_text)
        part_suffix = len(parts) > 1

        for part_idx, part_text in enumerate(parts):
            part_label = f" (Part {part_idx + 1})" if part_suffix else ""
            chapter_title = f"Chapter {chapter.number}: {chapter.title}{part_label}"

            logger.info(
                f"Synthesizing: {chapter_title} "
                f"({len(part_text)} chars)"
            )

            # Synthesize
            result: AudioResult = await tts.synthesize(
                part_text,
                voice=voice,
                ssml_options=ssml_options,
                chapter_title=chapter_title,
            )

            # Upload to blob storage
            blob_name = (
                f"audiobooks/{input.book_id}/"
                f"chapter-{chapter.number:03d}"
                f"{f'-part-{part_idx + 1:02d}' if part_suffix else ''}.mp3"
            )
            blob_uri = await ctx.blob.upload_bytes(
                result.audio_bytes,
                blob_name,
                content_type="audio/mpeg",
            )

            # Upload word boundaries if available
            wb_uri = ""
            if result.word_boundaries:
                import json

                wb_data = json.dumps(
                    [
                        {"text": wb.text, "start_ms": wb.start_ms, "end_ms": wb.end_ms}
                        for wb in result.word_boundaries
                    ]
                ).encode()
                wb_blob_name = blob_name.replace(".mp3", "-boundaries.json")
                wb_uri = await ctx.blob.upload_bytes(
                    wb_data, wb_blob_name, content_type="application/json"
                )

            chapter_audio = ChapterAudio(
                chapter_number=chapter.number,
                title=f"{chapter.title}{part_label}",
                blob_uri=blob_uri,
                duration_ms=result.duration_ms,
                file_size_bytes=len(result.audio_bytes),
                word_boundaries_uri=wb_uri,
            )
            chapters_audio.append(chapter_audio)
            total_cost += result.cost_estimate

            logger.info(
                f"  ✓ {chapter_title}: {result.duration_ms / 1000:.1f}s, "
                f"${result.cost_estimate:.4f}"
            )

    total_duration = sum(ch.duration_ms for ch in chapters_audio)

    logger.info(
        f"Audiobook complete: {len(chapters_audio)} files, "
        f"{total_duration / 1000 / 60:.1f} min total, "
        f"${total_cost:.2f} estimated cost"
    )

    return AudiobookOutput(
        book_id=input.book_id,
        chapters=chapters_audio,
        total_duration_ms=total_duration,
        total_cost=total_cost,
    )
