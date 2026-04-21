"""Stage 6: Assemble — Document reassembly into structured manuscript."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from transpose.pipeline.translate import (
    ORIGINAL_TEXT_FALLBACK_PREFIX,
    TRANSLATION_FAILED_PLACEHOLDER,
)
from transpose.utils import escape_html as _escape_html


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
    untranslated_passages = 0  # track for foreword note

    for chapter_num, (chapter_ref, chapter_chunks) in enumerate(
        sorted(chapters_data.items()), start=1
    ):
        # Extract English chapter title from first translated chunk
        # The original chapter_ref is in Devanagari; we need the English title
        english_title = _extract_chapter_title(chapter_chunks, chapter_ref)
        
        # Build chapter HTML (use English title in h1, with anchor ID for ToC links)
        chapter_id = f"chapter-{chapter_num}"
        content_html = "<div class='chapter'>\n"
        content_html += f"<h1 id='{chapter_id}'>{_escape_html(english_title)}</h1>\n"

        # Sub-heading counter for within-chapter headings (Discourse N, Part N, etc.)
        sub_heading_idx = 0

        for item_idx, item in enumerate(chapter_chunks):
            chunk = item["chunk"]
            translation = item["translation"]

            text = translation.translated_text

            # --- Issue #59: sanitize failure markers ---
            if TRANSLATION_FAILED_PLACEHOLDER in text:
                # Replace raw failure marker with original text fallback
                text = text.replace(
                    TRANSLATION_FAILED_PLACEHOLDER,
                    f"{ORIGINAL_TEXT_FALLBACK_PREFIX}\n\n{chunk.source_text}",
                )
                untranslated_passages += 1

            # Count passages that used the original-text fallback path
            if ORIGINAL_TEXT_FALLBACK_PREFIX in text:
                # Already counted above if we just replaced; also count if
                # translate stage stored it this way directly
                if TRANSLATION_FAILED_PLACEHOLDER not in translation.translated_text:
                    untranslated_passages += 1

            # Strip duplicate chapter title from first chunk's text.
            # The LLM translation often starts with "Chapter N: Title — ..."
            # which duplicates the <h1> we already rendered above.
            if item_idx == 0:
                text = _strip_leading_chapter_title(text)

            # Convert text to paragraphs, detecting sub-headings (Issue #57)
            paragraphs = text.split("\n\n")
            for para in paragraphs:
                stripped = para.strip()
                if not stripped:
                    continue

                # Check if this paragraph is a sub-heading
                heading_match = _detect_heading(stripped)
                if heading_match:
                    sub_heading_idx += 1
                    sub_id = f"{chapter_id}-s{sub_heading_idx}"
                    content_html += (
                        f"<h2 id='{sub_id}'>{_escape_html(stripped)}</h2>\n"
                    )
                    # Add sub-heading to TOC
                    toc.append({
                        "chapter": chapter_num,
                        "title": stripped,
                        "level": 2,
                        "anchor": sub_id,
                    })
                elif ORIGINAL_TEXT_FALLBACK_PREFIX in stripped:
                    # Render original text in a styled note block
                    content_html += (
                        "<div class='untranslated-note'>"
                        f"<p><em>{_escape_html(stripped)}</em></p>"
                        "</div>\n"
                    )
                else:
                    content_html += f"<p>{_escape_html(stripped)}</p>\n"

        content_html += "</div>\n"

        chapter = ManuscriptChapter(
            number=chapter_num,
            title=english_title,
            content_html=content_html,
        )
        chapters.append(chapter)

        # Add to TOC (with English title) — level-1 entry
        toc.append({"chapter": chapter_num, "title": english_title})

    # Derive the manuscript title from the translated content, not the
    # ingested filename which is often a placeholder like "Test Hindi Book".
    translated_title = _extract_book_title(translations, book.title, chunks)

    # Create manuscript
    manuscript = Manuscript(
        book_id=input.book_id,
        title=translated_title,
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
            foreword_text = await _generate_foreword(ctx, translated_title, cultural_terms)
            foreword_text = _clean_foreword(foreword_text)
            # Append note about untranslated passages if any
            if untranslated_passages > 0:
                foreword_text += (
                    f"\n\nNote: {untranslated_passages} passage(s) in this text could not "
                    "be fully translated due to content processing limitations. These "
                    "passages are presented in their original language and marked "
                    "accordingly."
                )
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
        title=translated_title,
        author=book.author,
        chapters=output_chapters,
        glossary_id=glossary_id,
        table_of_contents=toc,
        foreword=foreword_text,
    )


def _extract_book_title(translations: list, fallback: str, chunks: list | None = None) -> str:
    """Derive the book title from the earliest translated chunk.

    The first translated chunk typically contains the source PDF's title page
    or opening heading.  We look for a prominent title-like line that is NOT
    a chapter heading (``Chapter N: ...``).  If nothing suitable is found we
    fall back to ``book.title`` (which may be a filename placeholder).
    """
    import re

    if not translations:
        return fallback

    # Build a chunk-id → sequence map so we iterate in document order.
    chunk_seq: dict = {}
    if chunks:
        for c in chunks:
            chunk_seq[c.id] = getattr(c, "sequence", 0)

    sorted_translations = sorted(
        translations,
        key=lambda t: chunk_seq.get(t.chunk_id, 0),
    )

    for t in sorted_translations[:3]:
        text = t.translated_text
        if not text:
            continue
        for line in text.split("\n")[:5]:
            line = line.strip()
            if not line or len(line) < 5:
                continue
            # Skip chapter headings — we want the BOOK title
            if re.match(r"^Chapter\s+\d+", line, re.IGNORECASE):
                continue
            # Skip "Introduction" standalone
            if re.match(r"^Introduction$", line, re.IGNORECASE):
                continue

            # If the line contains multiple em-dashes, the title + subtitle
            # are in the first two segments; the rest is description.
            segments = [s.strip() for s in line.split("\u2014")]
            if len(segments) >= 2:
                candidate = " \u2014 ".join(segments[:2])
                if len(candidate) < 120:
                    return candidate

            # Accept short lines that look like titles
            if len(line) < 120 and re.match(r"^[A-Z]", line):
                return line

    return fallback


def _extract_chapter_title(chapter_chunks: list[dict], fallback: str) -> str:
    """Extract English chapter title from translated content.

    Looks for patterns like "Chapter N: Title" or just uses first line.
    Handles multi-line titles where the subtitle (after an em-dash) is on
    a separate line, e.g.::

        Chapter 1: Dharma and Karma
        — The Message of the Gita

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

    lines = text.split("\n")
    non_empty = [(i, line.strip()) for i, line in enumerate(lines) if line.strip()]

    for pos, (orig_idx, line) in enumerate(non_empty[:3]):
        # Match "Chapter N: Title — Subtitle" (single-line form)
        chapter_match = re.match(r"^(Chapter \d+:.+)", line, re.IGNORECASE)
        if chapter_match:
            title = chapter_match.group(1).strip()
            # Check if the NEXT non-empty line is a subtitle continuation
            # (starts with em-dash, en-dash, or long dash)
            title = _join_subtitle_line(title, non_empty, pos)
            if len(title) < 200:
                return title

        # Check if it's a standalone title-like line (all caps or title case)
        is_title_like = (
            re.match(r"^[A-Z][^a-z]*$", line)
            or re.match(r"^[A-Z][a-zA-Z\s:—\u2013\u2014-]+$", line)
        )
        if is_title_like and len(line) < 200:
            return line

    # Fallback: use first non-empty line
    for _idx, line in non_empty[:5]:
        if len(line) < 100:
            return line

    return fallback


def _join_subtitle_line(
    title: str, non_empty: list[tuple[int, str]], current_pos: int
) -> str:
    """Append a subtitle continuation line if the next line starts with a dash.

    Handles the common LLM pattern where the subtitle is on a separate line::

        Chapter 2: Yoga and Meditation
        — Physical and Spiritual Discipline
    """
    if current_pos + 1 < len(non_empty):
        _next_idx, next_line = non_empty[current_pos + 1]
        # em-dash (—), en-dash (–), or hyphen-minus (-)
        if next_line and next_line[0] in ("\u2014", "\u2013", "-"):
            title = title + " " + next_line
    return title


def _strip_leading_chapter_title(text: str) -> str:
    """Remove a leading chapter-title line (and optional subtitle) from translated text.

    The LLM translation often starts with one or two lines like::

        Chapter 2: Yoga and Meditation
        — Physical and Spiritual Discipline

    which would duplicate the ``<h1>`` already rendered by the assemble stage.
    This helper strips those leading lines, returning the remaining content.
    """
    import re

    lines = text.split("\n")
    first = lines[0].strip() if lines else ""
    # Matches "Chapter N: ..." or "Introduction"
    if not re.match(r"^(Chapter\s+\d+\b|Introduction\b)", first, re.IGNORECASE):
        return text

    # Strip the chapter title line
    remaining = lines[1:]
    # Also strip a subtitle continuation line (starts with em-/en-dash)
    while remaining:
        candidate = remaining[0].strip()
        if not candidate:
            remaining = remaining[1:]
            continue
        if candidate and candidate[0] in ("\u2014", "\u2013", "-"):
            remaining = remaining[1:]
        else:
            break

    return "\n".join(remaining).lstrip("\n") if remaining else ""


def _clean_foreword(text: str) -> str:
    """Remove LLM-generated placeholder sign-offs from the foreword.

    GPT-4o often appends lines like ``Warm regards, [Translator's Name]``
    even when asked not to.  Strip them so the output looks polished.
    """
    import re

    # Remove trailing lines that contain bracketed placeholders
    lines = text.rstrip().split("\n")
    while lines and re.search(r"\[.*?name.*?\]", lines[-1], re.IGNORECASE):
        lines.pop()
    # Also remove a bare sign-off line left orphaned (e.g. "Warm regards,")
    sign_off = r"^(Warm regards|Sincerely|With .* regards|Yours),?\s*$"
    while lines and re.match(sign_off, lines[-1].strip(), re.IGNORECASE):
        lines.pop()
    return "\n".join(lines).rstrip()


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
        f"— it will be added separately. Do not include a "
        f"sign-off with a placeholder name like '[Translator\\'s Name]' "
        f"— end naturally without a signature block."
    )

    return await ctx.llm.chat(prompt)


# ---------------------------------------------------------------------------
# Heading detection for Issue #57 (multi-level TOC)
# ---------------------------------------------------------------------------

# Patterns that identify discourse/chapter sub-headings in translated text
_HEADING_PATTERNS: list[re.Pattern] = [
    re.compile(r"^Discourse\s+\d+", re.IGNORECASE),
    re.compile(r"^Part\s+[IVXLCDM\d]+", re.IGNORECASE),
    re.compile(r"^Section\s+\d+", re.IGNORECASE),
    re.compile(r"^Lecture\s+\d+", re.IGNORECASE),
    re.compile(r"^Talk\s+\d+", re.IGNORECASE),
    re.compile(r"^Sermon\s+\d+", re.IGNORECASE),
    re.compile(r"^Session\s+\d+", re.IGNORECASE),
    # Numbered heading like "1. The Nature of Reality" or "15. Beyond the Mind"
    re.compile(r"^\d{1,3}\.\s+[A-Z]"),
]


def _detect_heading(text: str) -> bool:
    """Return True if *text* looks like a discourse/section heading.

    Only short lines (< 120 chars) are considered — long paragraphs that
    happen to start with "Discourse" are not headings.
    """
    if len(text) > 120:
        return False
    # Must be a single line (no internal line breaks)
    if "\n" in text:
        return False
    return any(p.match(text) for p in _HEADING_PATTERNS)
