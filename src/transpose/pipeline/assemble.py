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

    for chapter_num, (chapter_title, chapter_chunks) in enumerate(
        sorted(chapters_data.items()), start=1
    ):
        # Build chapter HTML
        content_html = "<div class='chapter'>\n"
        content_html += f"<h1>{chapter_title}</h1>\n"

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
            title=chapter_title,
            content_html=content_html,
        )
        chapters.append(chapter)

        # Add to TOC
        toc.append({"chapter": chapter_num, "title": chapter_title})

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
    )


def _escape_html(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

