"""Stage 6: Assemble — Document reassembly into structured manuscript."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class AssembleInput:
    book_id: UUID
    glossary_position: str = "back"  # "front" or "back"


@dataclass
class Chapter:
    number: int
    title: str
    content_html: str


@dataclass
class AssembleOutput:
    book_id: UUID
    manuscript_id: UUID
    title: str
    author: str | None
    chapters: list[Chapter] = field(default_factory=list)
    glossary_id: UUID | None = None
    table_of_contents: list[dict] = field(default_factory=list)
    foreword: str | None = None


async def run(input: AssembleInput, ctx) -> AssembleOutput:  # type: ignore[no-untyped-def]
    """Reassemble translated chunks into a structured manuscript.

    Reconstructs chapters, generates TOC, inserts glossary,
    cleans up cross-chunk boundaries.
    """
    import logging
    from collections import defaultdict

    from transpose.models.enums import BookStatus, SectionType
    from transpose.models.manuscript import Chapter as ManuscriptChapter
    from transpose.models.manuscript import Manuscript

    logger = logging.getLogger(__name__)

    # Get book
    book = await ctx.db.get_book(input.book_id)
    if not book:
        raise ValueError(f"Book not found: {input.book_id}")

    logger.info(f"Assembling manuscript for: {book.title}")

    # Get chunks and translations
    chunks = await ctx.db.get_chunks_for_book(input.book_id)
    translations = await ctx.db.get_translations_for_book(input.book_id)

    # Get glossary
    glossary = await ctx.db.get_glossary_for_book(input.book_id)
    glossary_id = glossary.id if glossary else None

    # Build translation map
    translation_map = {t.chunk_id: t for t in translations}

    # Group chunks by chapter
    chapters_data: dict[str, list] = defaultdict(list)
    current_chapter = "Introduction"

    for chunk in chunks:
        # Update current chapter if this chunk starts a new chapter
        if chunk.section_type == SectionType.CHAPTER and chunk.chapter_ref:
            current_chapter = chunk.chapter_ref

        # Get translation
        translation = translation_map.get(chunk.id)
        if translation:
            chapters_data[current_chapter].append(
                {"chunk": chunk, "translation": translation}
            )

    # Build chapters
    chapters: list[ManuscriptChapter] = []
    toc: list[dict] = []

    for chapter_num, (chapter_ref, chapter_chunks) in enumerate(
        sorted(chapters_data.items()), start=1
    ):
        # Extract English chapter title from first translated chunk
        # The original chapter_ref is in Devanagari; we need the English title
        english_title = _extract_chapter_title(chapter_chunks, chapter_ref)
        
        # Build chapter HTML (use English title in h1)
        content_html = "<div class='chapter'>\n"
        content_html += f"<h1>{_escape_html(english_title)}</h1>\n"

        for item in chapter_chunks:
            chunk = item["chunk"]
            translation = item["translation"]

            # Convert text to paragraphs
            paragraphs = translation.translated_text.split("\n\n")
            for para in paragraphs:
                if para.strip():
                    content_html += f"<p>{_escape_html(para.strip())}</p>\n"

        content_html += "</div>\n"

        chapter = ManuscriptChapter(
            number=chapter_num,
            title=english_title,
            content_html=content_html,
        )
        chapters.append(chapter)

        # Add to TOC (with English title)
        toc.append({"chapter": chapter_num, "title": english_title})

    # Create manuscript
    manuscript = Manuscript(
        book_id=input.book_id,
        title=book.title,
        author=book.author,
        chapters=chapters,
        glossary_id=glossary_id or book.id,  # fallback to book ID
        table_of_contents=toc,
        metadata={
            "source_language": book.source_language.value,
            "total_chunks": len(chunks),
            "total_chapters": len(chapters),
        },
    )

    # Generate Translator's Foreword using cultural terms from glossary
    foreword_text = None
    if glossary and glossary.entries:
        cultural_terms = [
            {"term": e.term, "original_script": e.original_script, "definition": e.definition}
            for e in sorted(glossary.entries, key=lambda e: e.occurrence_count, reverse=True)
        ]
        try:
            foreword_text = await _generate_foreword(ctx, book.title, cultural_terms)
            manuscript.metadata["foreword"] = foreword_text
            logger.info("Generated Translator's Foreword (%d chars)", len(foreword_text))
        except Exception:
            logger.warning("Failed to generate foreword — continuing without it", exc_info=True)

    await ctx.db.create_manuscript(manuscript)

    logger.info(f"Created manuscript with {len(chapters)} chapters")

    # Update book status
    await ctx.db.update_book_status(input.book_id, BookStatus.ASSEMBLED)

    # Build output
    output_chapters = [
        Chapter(
            number=chapter.number,
            title=chapter.title,
            content_html=chapter.content_html,
        )
        for chapter in chapters
    ]

    return AssembleOutput(
        book_id=input.book_id,
        manuscript_id=manuscript.id,
        title=book.title,
        author=book.author,
        chapters=output_chapters,
        glossary_id=glossary_id,
        table_of_contents=toc,
        foreword=foreword_text,
    )


def _extract_chapter_title(chapter_chunks: list[dict], fallback: str) -> str:
    """Extract English chapter title from translated content.
    
    Looks for patterns like "Chapter N: Title" or just uses first line.
    Falls back to the provided fallback if extraction fails.
    """
    import re
    
    if not chapter_chunks:
        return fallback
    
    # Get first translation
    first_translation = chapter_chunks[0].get("translation")
    if not first_translation:
        return fallback
    
    text = first_translation.translated_text
    if not text:
        return fallback
    
    # Try to extract "Chapter N: Title" or "Introduction" pattern
    lines = text.split("\n")
    for line in lines[:3]:  # Check first 3 lines
        line = line.strip()
        if not line:
            continue
            
        # Match "Chapter N: Title" or "Introduction" or similar
        chapter_match = re.match(r"^(Chapter \d+:.*?)(?:\s*—|$)", line, re.IGNORECASE)
        if chapter_match:
            return chapter_match.group(1).strip()
        
        # Check if it's a standalone title-like line (all caps or title case)
        if re.match(r"^[A-Z][^a-z]*$", line) or re.match(r"^[A-Z][a-zA-Z\s:—-]+$", line):
            # Remove common separator patterns
            title = re.sub(r"\s*—.*$", "", line)
            if len(title) < 100:  # Reasonable title length
                return title.strip()
    
    # Fallback: use first non-empty line
    for line in lines[:5]:
        line = line.strip()
        if line and len(line) < 100:
            return line
    
    return fallback


def _escape_html(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


async def _generate_foreword(ctx, book_title: str, cultural_terms: list[dict]) -> str:
    """Generate a Translator's Foreword using the LLM.

    The foreword explains the cultural translation philosophy and contextualises
    the preserved original-language words for the reader.
    """
    terms_list = ", ".join(t["term"] for t in cultural_terms[:15])

    prompt = (
        f'Write a Translator\'s Foreword (250-400 words) for the '
        f'English translation of "{book_title}".\n\n'
        f"This foreword should:\n"
        f"1. Explain the literary and cultural translation approach "
        f"— not a literal translation but a cultural bridge\n"
        f"2. Explain why certain words are preserved in their "
        f"original language: {terms_list}\n"
        f"3. Help the reader understand these preserved words add "
        f"authenticity and cultural depth\n"
        f"4. Be written in a warm, scholarly tone appropriate for "
        f"a published eBook\n"
        f'5. Address the reader directly ("Dear Reader" or similar)\n\n'
        f"Write ONLY the foreword text. Do not include a title "
        f"— it will be added separately."
    )

    return await ctx.llm.chat(prompt)

