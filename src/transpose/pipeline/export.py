"""Stage 7: Export — ePub and PDF rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from transpose.utils import escape_html as _escape_html
from transpose.utils.unicode import normalize_unicode


@dataclass
class ExportInput:
    book_id: UUID
    formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])


@dataclass
class ExportArtifact:
    format: str
    blob_uri: str
    file_size_bytes: int


@dataclass
class ExportOutput:
    book_id: UUID
    artifacts: list[ExportArtifact] = field(default_factory=list)


async def run(input: ExportInput, ctx) -> ExportOutput:  # type: ignore[no-untyped-def]
    """Render the manuscript into ePub and/or PDF.

    ePub: ebooklib with semantic HTML chapters.
    PDF: weasyprint from the same HTML source.
    Both stored in Azure Blob Storage.
    """
    import logging

    from transpose.models.enums import BookStatus

    logger = logging.getLogger(__name__)

    # Get book
    book = await ctx.db.get_book(input.book_id)
    if not book:
        raise ValueError(f"Book not found: {input.book_id}")

    # Get manuscript
    manuscript = await ctx.db.get_manuscript_for_book(input.book_id)
    if not manuscript:
        raise ValueError(f"No manuscript found for book: {input.book_id}")

    # Get glossary
    glossary = await ctx.db.get_glossary_for_book(input.book_id)

    logger.info(f"Exporting manuscript for: {book.title}")

    # --- Issue #55: Retrieve cover image if available ---
    cover_image_data: bytes | None = None
    cover_image_uri = (manuscript.metadata or {}).get("cover_image_uri")
    if not cover_image_uri:
        # Try book metadata via raw DB query (set by OCR stage)
        try:
            logger.debug("Cover not in manuscript metadata — checking book metadata")
            row = await ctx.db.fetch_one(
                "SELECT metadata->>'cover_image_uri' AS uri FROM books WHERE id = $1",
                input.book_id,
            )
            if row and row.get("uri"):
                cover_image_uri = row["uri"]
                logger.info("Found cover_image_uri in book metadata: %s", cover_image_uri)
            else:
                logger.info("No cover_image_uri found in book metadata")
        except Exception as e:
            logger.warning("Failed to query book metadata for cover image: %s", e)

    if cover_image_uri:
        try:
            cover_blob_name = cover_image_uri.split("/")[-1]
            logger.info("Downloading cover image: %s from container %s", 
                       cover_blob_name, ctx.settings.blob_container_source)
            cover_image_data = await ctx.blob.download_blob(
                container=ctx.settings.blob_container_source,
                blob_name=cover_blob_name,
            )
            logger.info("Loaded cover image: %d bytes", len(cover_image_data))
        except Exception as e:
            logger.warning("Could not download cover image (blob: %s) — using text title page. Error: %s", 
                         cover_blob_name, e, exc_info=True)

    artifacts: list[ExportArtifact] = []

    # Generate ePub if requested
    if "epub" in input.formats:
        epub_data = await _generate_epub(manuscript, glossary, book, cover_image_data)
        epub_name = f"{_sanitize_filename(book.title)}.epub"

        # Upload to blob storage
        epub_uri = await ctx.blob.upload_output(
            container=ctx.settings.blob_container_output,
            blob_name=epub_name,
            data=epub_data,
        )

        artifacts.append(
            ExportArtifact(
                format="epub",
                blob_uri=epub_uri,
                file_size_bytes=len(epub_data),
            )
        )
        logger.info(f"Generated ePub: {len(epub_data)} bytes")

    # Generate PDF if requested
    if "pdf" in input.formats:
        pdf_data = await _generate_pdf(manuscript, glossary, book, cover_image_data)
        pdf_name = f"{_sanitize_filename(book.title)}.pdf"

        # Upload to blob storage
        pdf_uri = await ctx.blob.upload_output(
            container=ctx.settings.blob_container_output,
            blob_name=pdf_name,
            data=pdf_data,
        )

        artifacts.append(
            ExportArtifact(
                format="pdf",
                blob_uri=pdf_uri,
                file_size_bytes=len(pdf_data),
            )
        )
        logger.info(f"Generated PDF: {len(pdf_data)} bytes")

    # Update book status
    await ctx.db.update_book_status(input.book_id, BookStatus.EXPORTED)

    logger.info(f"Export complete: {len(artifacts)} artifacts")

    return ExportOutput(
        book_id=input.book_id,
        artifacts=artifacts,
    )


async def _generate_epub(manuscript, glossary, book, cover_image_data: bytes | None = None) -> bytes:
    """Generate ePub file from manuscript."""
    import io

    from ebooklib import epub

    # Create book
    ebook = epub.EpubBook()
    ebook.set_identifier(str(manuscript.id))
    ebook.set_title(manuscript.title)
    if manuscript.author:
        ebook.set_language("en")
        ebook.add_author(manuscript.author)

    # Add CSS
    css = """
    body { font-family: Georgia, serif; line-height: 1.6; }
    h1 { font-size: 2em; margin-top: 2em; }
    h2 { font-size: 1.5em; margin-top: 1.5em; }
    p { margin: 1em 0; text-align: justify; }
    .glossary-term { font-weight: bold; }
    .chapter { margin-bottom: 2em; }
    .foreword-content p { text-indent: 1.5em; margin: 0.5em 0; font-style: italic; }
    .cover-title { font-size: 2.5em; font-weight: bold; text-align: center;
                   letter-spacing: 2px; margin-top: 4em; margin-bottom: 0.5em; }
    .cover-subtitle { font-size: 1.5em; font-style: italic; text-align: center;
                      color: #444; margin-bottom: 2em; }
    .cover-separator { border: none; border-top: 2px solid #666;
                       width: 40%; margin: 2em auto; }
    .cover-author { font-size: 1.2em; text-align: center;
                    margin-top: 2em; letter-spacing: 1px; }
    """
    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=css,
    )
    ebook.add_item(nav_css)

    # --- Issue #55: Use cover image if available ---
    epub_chapters = []
    if cover_image_data:
        # Add the cover image as an ePub item
        cover_img_item = epub.EpubItem(
            uid="cover-image",
            file_name="images/cover.png",
            media_type="image/png",
            content=cover_image_data,
        )
        ebook.add_item(cover_img_item)
        ebook.set_cover("images/cover.png", cover_image_data)

        cover_html = (
            "<div style='text-align: center;'>\n"
            "<img src='images/cover.png' alt='Cover' "
            "style='max-width:100%; max-height:95vh;'/>\n"
            "</div>\n"
        )
        cover_page = epub.EpubHtml(
            title="Cover",
            file_name="cover.xhtml",
            lang="en",
        )
        cover_page.content = cover_html
        cover_page.add_item(nav_css)
        ebook.add_item(cover_page)
        epub_chapters.append(cover_page)
    else:
        # Text-only cover page fallback — Issue #10
        subtitle = (manuscript.metadata or {}).get("subtitle", "")
        cover_html = "<div style='text-align: center;'>\n"
        cover_html += f"<div class='cover-title'>{manuscript.title}</div>\n"
        if subtitle:
            cover_html += f"<div class='cover-subtitle'>{subtitle}</div>\n"
        cover_html += "<hr class='cover-separator'>\n"
        if manuscript.author:
            cover_html += f"<div class='cover-author'>{manuscript.author}</div>\n"
        cover_html += "</div>\n"

        cover_page = epub.EpubHtml(
            title="Cover",
            file_name="cover.xhtml",
            lang="en",
        )
        cover_page.content = cover_html
        cover_page.add_item(nav_css)
        ebook.add_item(cover_page)
        epub_chapters.append(cover_page)

    # Add Translator's Note if present (Issue #64 — factual, not AI-generated)
    translator_note = manuscript.metadata.get("translator_note") if manuscript.metadata else None
    if translator_note:
        note_html = "<h1>Translator's Note</h1>\n<div class='foreword-content'>\n"
        for para in translator_note.split("\n\n"):
            if para.strip():
                note_html += f"<p>{para.strip()}</p>\n"
        note_html += "</div>\n"

        note_chapter = epub.EpubHtml(
            title="Translator's Note",
            file_name="translator_note.xhtml",
            lang="en",
        )
        note_chapter.content = note_html
        note_chapter.add_item(nav_css)
        ebook.add_item(note_chapter)
        epub_chapters.append(note_chapter)

    # Add chapters
    for chapter in manuscript.chapters:
        epub_chapter = epub.EpubHtml(
            title=chapter.title,
            file_name=f"chapter_{chapter.number}.xhtml",
            lang="en",
        )
        epub_chapter.content = chapter.content_html
        epub_chapter.add_item(nav_css)
        ebook.add_item(epub_chapter)
        epub_chapters.append(epub_chapter)

    # Add glossary if available
    if glossary and glossary.entries:
        glossary_html = "<h1>Glossary</h1>\n<dl>\n"
        for entry in sorted(glossary.entries, key=lambda e: e.term):
            glossary_html += f"<dt class='glossary-term'>{entry.term}"
            if entry.original_script:
                glossary_html += f" ({normalize_unicode(entry.original_script)})"
            glossary_html += f"</dt>\n<dd>{entry.definition}</dd>\n"
        glossary_html += "</dl>\n"

        glossary_chapter = epub.EpubHtml(
            title="Glossary",
            file_name="glossary.xhtml",
            lang="en",
        )
        glossary_chapter.content = glossary_html
        glossary_chapter.add_item(nav_css)
        ebook.add_item(glossary_chapter)
        epub_chapters.append(glossary_chapter)

    # Define Table of Contents
    ebook.toc = tuple(epub_chapters)

    # Add navigation files
    ebook.add_item(epub.EpubNcx())
    ebook.add_item(epub.EpubNav())

    # Define spine (reading order)
    ebook.spine = ["nav"] + epub_chapters

    # Write to bytes
    output = io.BytesIO()
    epub.write_epub(output, ebook)
    return output.getvalue()


async def _generate_pdf(manuscript, glossary, book, cover_image_data: bytes | None = None) -> bytes:
    """Generate PDF file from manuscript HTML.

    Uses a two-pass approach:
      Pass 1 — render with placeholder ToC to discover actual chapter page numbers.
      Pass 2 — re-render with hard-coded page numbers for reliable ToC display.

    Embeds Noto Sans Devanagari (static) and Noto Sans Gurmukhi fonts via
    @font-face with unicode-range so that all Indic script glossary entries
    render correctly.  All text is NFC-normalized before rendering to prevent
    halant misordering and combining-mark issues.
    """
    import logging
    from pathlib import Path

    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    logger = logging.getLogger(__name__)

    # --- Font paths (static font preferred for reliable GSUB/GPOS shaping) ---
    fonts_dir = Path(__file__).resolve().parents[3] / "fonts"
    devanagari_font = fonts_dir / "NotoSansDevanagari-Regular.ttf"
    gurmukhi_font = fonts_dir / "NotoSansGurmukhi.ttf"

    # Build reusable HTML fragments
    body_html = _build_pdf_body_html(manuscript, glossary)

    # --- Pass 1: render with placeholder ToC to discover page positions ---
    font_config_1 = FontConfiguration()
    css_pass1 = _build_pdf_css(
        devanagari_font, gurmukhi_font, font_config_1, use_target_counter=True
    )
    toc_html_pass1 = _build_toc_html(manuscript.table_of_contents, page_map=None)
    full_html_1 = _assemble_full_html(manuscript, toc_html_pass1, body_html, cover_image_data)
    full_html_1 = normalize_unicode(full_html_1)

    pdf_pass1 = HTML(string=full_html_1).write_pdf(
        stylesheets=[css_pass1], font_config=font_config_1
    )

    # Extract chapter→page mapping from the pass-1 PDF
    page_map = _extract_chapter_page_numbers(pdf_pass1)
    logger.info("ToC page map from pass 1: %s", page_map)

    # --- Pass 2: render with hard-coded page numbers ---
    font_config_2 = FontConfiguration()
    css_pass2 = _build_pdf_css(
        devanagari_font, gurmukhi_font, font_config_2, use_target_counter=False
    )
    toc_html_pass2 = _build_toc_html(manuscript.table_of_contents, page_map=page_map)
    full_html_2 = _assemble_full_html(manuscript, toc_html_pass2, body_html, cover_image_data)
    full_html_2 = normalize_unicode(full_html_2)

    pdf_bytes = HTML(string=full_html_2).write_pdf(
        stylesheets=[css_pass2], font_config=font_config_2
    )
    return pdf_bytes


def _build_pdf_css(devanagari_font, gurmukhi_font, font_config, *, use_target_counter):
    """Build the WeasyPrint CSS stylesheet.

    When *use_target_counter* is True (pass 1), the ToC ``::after`` uses
    ``target-counter()`` so WeasyPrint resolves page numbers.  In pass 2 the
    ``::after`` is suppressed because hard-coded ``<span>`` page numbers are
    injected into the HTML instead.
    """
    from weasyprint import CSS

    # ToC page-number display strategy per pass
    toc_after = (
        "content: target-counter(attr(href url), page);"
        if use_target_counter
        else "content: none;"
    )

    # Gurmukhi font-face (only if font exists on disk)
    gurmukhi_face = ""
    if gurmukhi_font and gurmukhi_font.exists():
        gurmukhi_face = f"""
        @font-face {{
            font-family: 'Noto Sans Gurmukhi';
            src: url('file://{gurmukhi_font}') format('truetype');
            font-weight: normal;
            font-style: normal;
            unicode-range: U+0A00-0A7F;
        }}
        @font-face {{
            font-family: 'Noto Sans Gurmukhi';
            src: url('file://{gurmukhi_font}') format('truetype');
            font-weight: bold;
            font-style: normal;
            unicode-range: U+0A00-0A7F;
        }}
        """

    css_text = f"""
    @font-face {{
        font-family: 'Noto Sans Devanagari';
        src: url('file://{devanagari_font}') format('truetype');
        font-weight: normal;
        font-style: normal;
        unicode-range: U+0900-097F, U+A8E0-A8FF, U+1CD0-1CFF;
    }}
    @font-face {{
        font-family: 'Noto Sans Devanagari';
        src: url('file://{devanagari_font}') format('truetype');
        font-weight: bold;
        font-style: normal;
        unicode-range: U+0900-097F, U+A8E0-A8FF, U+1CD0-1CFF;
    }}
    {gurmukhi_face}
    @page {{
        size: A4;
        margin: 2.5cm;
        @bottom-center {{
            content: counter(page);
            font-size: 10pt;
            color: #666;
        }}
    }}
    @page :first {{
        @bottom-center {{
            content: none;
        }}
    }}
    .title-page, .toc-page, .foreword-page {{
        page: frontmatter;
    }}
    @page frontmatter {{
        @bottom-center {{
            content: counter(page, lower-roman);
            font-size: 10pt;
            color: #666;
        }}
    }}
    body {{
        font-family: Georgia, 'Noto Sans Devanagari', 'Noto Sans Gurmukhi', serif;
        line-height: 1.6;
        font-size: 12pt;
    }}
    h1 {{
        font-size: 24pt;
        margin-top: 2em;
        page-break-before: always;
    }}
    h1:first-of-type {{
        page-break-before: avoid;
    }}
    h2 {{
        font-size: 18pt;
        margin-top: 1.5em;
    }}
    p {{
        margin: 1em 0;
        text-align: justify;
    }}
    .title-page {{
        text-align: center;
        padding-top: 3cm;
        page-break-after: always;
    }}
    .title {{
        font-size: 32pt;
        font-weight: bold;
        letter-spacing: 2px;
        margin-bottom: 1em;
    }}
    .subtitle {{
        font-size: 20pt;
        font-style: italic;
        color: #444;
        margin-bottom: 2em;
    }}
    .title-separator {{
        border: none;
        border-top: 2px solid #666;
        width: 40%;
        margin: 2em auto;
    }}
    .author {{
        font-size: 16pt;
        margin-top: 3em;
        letter-spacing: 1px;
    }}
    .toc-page {{
        page-break-after: always;
    }}
    .toc-page h1 {{
        text-align: center;
        page-break-before: avoid;
    }}
    .toc {{
        list-style: none;
        padding: 0;
    }}
    .toc-entry {{
        list-style: none;
        padding: 0.5em 0;
        border-bottom: 1px dotted #ccc;
        font-size: 14pt;
        page-break-inside: avoid;
    }}
    .toc-entry a {{
        text-decoration: none;
        color: inherit;
        display: flex;
        justify-content: space-between;
    }}
    .toc-entry a::after {{
        {toc_after}
        font-style: normal;
    }}
    .glossary-term {{
        font-weight: bold;
    }}
    dl {{
        margin: 1em 0;
    }}
    dt {{
        font-weight: bold;
        margin-top: 0.5em;
    }}
    dd {{
        margin-left: 2em;
    }}
    .foreword-page {{
        page-break-after: always;
    }}
    .foreword-content p {{
        text-indent: 1.5em;
        margin: 0.5em 0;
        font-style: italic;
    }}
    .toc-sub {{
        padding-left: 2em;
        font-size: 12pt;
    }}
    .untranslated-note {{
        background: #f9f5e3;
        border-left: 3px solid #c9a94e;
        padding: 0.5em 1em;
        margin: 1em 0;
        font-style: italic;
    }}
    .cover-image {{
        text-align: center;
        page-break-after: always;
    }}
    .cover-image img {{
        max-width: 100%;
        max-height: 90vh;
    }}
    """
    return CSS(string=css_text, font_config=font_config)


def _build_toc_html(table_of_contents, *, page_map):
    """Build the Table of Contents HTML.

    When *page_map* is ``None`` (pass 1), links use ``#chapter-N`` anchors
    and CSS ``target-counter()`` supplies page numbers.  When *page_map* is
    provided (pass 2), a ``<span class='toc-page-num'>`` with the hard-coded
    page number is appended to each entry.
    """
    if not table_of_contents:
        return ""

    parts = ["<div class='toc-page'>\n", "<h1>Table of Contents</h1>\n", "<ul class='toc'>\n"]
    for toc_entry in table_of_contents:
        chapter_num = toc_entry.get("chapter", "")
        level = toc_entry.get("level", 1)
        # Use explicit anchor if provided (sub-headings), else chapter-N
        anchor = toc_entry.get("anchor", f"chapter-{chapter_num}")
        title = _escape_html(toc_entry["title"])

        # Indent sub-entries
        li_class = "toc-entry" if level == 1 else "toc-entry toc-sub"

        if page_map and chapter_num in page_map and level == 1:
            page_num = page_map[chapter_num]
            parts.append(
                f"<li class='{li_class}'>"
                f"<a href='#{anchor}'>"
                f"<span class='toc-title'>{title}</span>"
                f"<span class='toc-page-num'>{page_num}</span>"
                f"</a></li>\n"
            )
        else:
            parts.append(
                f"<li class='{li_class}'>"
                f"<a href='#{anchor}'>"
                f"<span class='toc-title'>{title}</span>"
                f"</a></li>\n"
            )
    parts.append("</ul>\n</div>\n")
    return "".join(parts)


def _build_pdf_body_html(manuscript, glossary):
    """Build the body HTML (translator's note + chapters + glossary)."""
    parts = []

    # Translator's Note — Issue #64 (replaces fabricated foreword)
    translator_note = manuscript.metadata.get("translator_note") if manuscript.metadata else None
    if translator_note:
        parts.append("<div class='foreword-page'>\n")
        parts.append("<h1>Translator's Note</h1>\n")
        parts.append("<div class='foreword-content'>\n")
        for para in translator_note.split("\n\n"):
            if para.strip():
                parts.append(f"<p>{_escape_html(para.strip())}</p>\n")
        parts.append("</div>\n</div>\n")

    # Reset page counter to arabic 1 at start of body content — Issue #11
    parts.append("<div style='counter-reset: page 1;'></div>\n")

    # Chapters
    for chapter in manuscript.chapters:
        parts.append(chapter.content_html)

    # Glossary — seed glossary overrides LLM-detected original_script at
    # render time so that curated Devanagari/Gurmukhi forms are always used,
    # even when the DB contains garbled LLM output.
    if glossary and glossary.entries:
        from transpose.config.seed_glossary import get_seed_glossary

        seed_terms = get_seed_glossary()
        parts.append("<h1>Glossary</h1>\n<dl>\n")
        for entry in sorted(glossary.entries, key=lambda e: e.term):
            parts.append(f"<dt class='glossary-term'>{_escape_html(entry.term)}")
            term_key = entry.term.lower().strip()
            script = entry.original_script
            if term_key in seed_terms and seed_terms[term_key][0]:
                script = seed_terms[term_key][0]
            if script:
                parts.append(
                    f" ({_escape_html(normalize_unicode(script))})"
                )
            parts.append(f"</dt>\n<dd>{_escape_html(entry.definition)}</dd>\n")
        parts.append("</dl>\n")

    return "".join(parts)


def _assemble_full_html(manuscript, toc_html, body_html, cover_image_data: bytes | None = None):
    """Combine title page, ToC, and body into a complete HTML document."""
    import base64

    parts = [
        "<!DOCTYPE html>\n<html>\n<head><meta charset='UTF-8'></head>\n<body>\n",
    ]

    # --- Issue #55: Cover image page (if available) ---
    if cover_image_data:
        b64 = base64.b64encode(cover_image_data).decode("ascii")
        parts.append("<div class='cover-image'>\n")
        parts.append(f"<img src='data:image/png;base64,{b64}' alt='Cover'/>\n")
        parts.append("</div>\n")
    else:
        # Text-only title page (cover) — Issue #10
        subtitle = (manuscript.metadata or {}).get("subtitle", "")
        parts.append("<div class='title-page'>\n")
        parts.append(f"<div class='title'>{_escape_html(manuscript.title)}</div>\n")
        if subtitle:
            parts.append(f"<div class='subtitle'>{_escape_html(subtitle)}</div>\n")
        parts.append("<hr class='title-separator'>\n")
        if manuscript.author:
            parts.append(f"<div class='author'>{_escape_html(manuscript.author)}</div>\n")
        parts.append("</div>\n")

    # ToC
    parts.append(toc_html)

    # Body (translator's note + chapters + glossary)
    parts.append(body_html)

    parts.append("</body></html>")
    return "".join(parts)


def _extract_chapter_page_numbers(pdf_bytes):
    """Extract chapter→page number mapping from rendered PDF bytes.

    Scans each page for "Chapter N:" headings and computes body-relative
    page numbers (subtracting the front-matter page count).  Returns a dict
    mapping chapter number (int or str matching the ToC key) to page number.

    Returns an empty dict if the PDF cannot be parsed (e.g. during tests
    with mock PDF bytes).
    """
    import re

    try:
        import fitz
    except ImportError:
        return {}

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return {}

    # Count front-matter pages (title, ToC, translator's note — before body content)
    frontmatter_pages = 0
    body_started = False
    chapter_pattern = re.compile(r"Chapter\s+(\d+)\s*:")

    page_map = {}
    for page_idx in range(doc.page_count):
        text = doc[page_idx].get_text()

        # Detect first chapter heading = start of body
        match = chapter_pattern.search(text)
        if match and not body_started:
            body_started = True
            frontmatter_pages = page_idx

        if match:
            chapter_num = int(match.group(1))
            body_page = page_idx - frontmatter_pages + 1
            page_map[chapter_num] = body_page

    doc.close()
    return page_map


def _sanitize_filename(filename: str) -> str:
    """Sanitize filename for blob storage."""
    import re

    # Remove invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', "", filename)
    # Replace spaces with underscores
    sanitized = sanitized.replace(" ", "_")
    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:100]
    return sanitized

