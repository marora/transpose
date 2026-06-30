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

    # --- Issue #67: Resolve blob image URIs to base64 data URIs ---
    await _resolve_chapter_images(manuscript, ctx, logger)

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
    ebook.set_title(book.title if book else manuscript.title)
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

    # Copyright / attribution page
    author_name = manuscript.author or "Unknown"
    copyright_html = (
        "<div style='text-align: center; padding-top: 6em;'>\n"
        f"<p><strong>{_escape_html(book.title if book else manuscript.title)}</strong></p>\n"
        f"<p>by {_escape_html(author_name)}</p>\n"
        "<br/>\n"
        f"<p>&copy; {_escape_html(author_name)} Foundation International</p>\n"
        "<p>English translation produced by Transpose AI Translation Pipeline</p>\n"
        "<br/>\n"
        "<p><em>All rights reserved. No part of this publication may be reproduced, "
        "stored in a retrieval system, or transmitted in any form or by any means "
        "without the prior written permission of the copyright holder.</em></p>\n"
        "<br/>\n"
        "<p>Cultural terms from the original language have been preserved "
        "to maintain authenticity. A glossary is provided at the end of this volume.</p>\n"
        "</div>\n"
    )
    copyright_page = epub.EpubHtml(
        title="Copyright",
        file_name="copyright.xhtml",
        lang="en",
    )
    copyright_page.content = copyright_html
    copyright_page.add_item(nav_css)
    ebook.add_item(copyright_page)
    epub_chapters.append(copyright_page)

    # Add Translator's Foreword if present
    foreword_text = manuscript.metadata.get("foreword") if manuscript.metadata else None
    if foreword_text:
        foreword_html = "<h1>Translator's Foreword</h1>\n<div class='foreword-content'>\n"
        for para in foreword_text.split("\n\n"):
            if para.strip():
                foreword_html += f"<p>{para.strip()}</p>\n"
        foreword_html += "</div>\n"

        foreword_chapter = epub.EpubHtml(
            title="Translator's Foreword",
            file_name="foreword.xhtml",
            lang="en",
        )
        foreword_chapter.content = foreword_html
        foreword_chapter.add_item(nav_css)
        ebook.add_item(foreword_chapter)
        epub_chapters.append(foreword_chapter)

    # Add chapters
    for chapter in manuscript.chapters:
        html = _postprocess_chapter_html(chapter.content_html)
        title = chapter.title
        epub_chapter = epub.EpubHtml(
            title=title,
            file_name=f"chapter_{chapter.number}.xhtml",
            lang="en",
        )
        epub_chapter.content = html
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

    # --- Font paths (variable font has better glyph coverage for conjuncts) ---
    fonts_dir = Path(__file__).resolve().parents[3] / "fonts"
    devanagari_font = fonts_dir / "NotoSansDevanagari.ttf"
    gurmukhi_font = fonts_dir / "NotoSansGurmukhi.ttf"

    # Build reusable HTML fragments
    body_html = _build_pdf_body_html(manuscript, glossary)

    # Attach book title for subtitle derivation in title page
    manuscript._book_title = book.title if book else manuscript.title

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

    # --- Post-process: set PDF metadata via PyMuPDF ---
    pdf_bytes = _set_pdf_metadata(pdf_bytes, manuscript, book)

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
        margin: 2cm;
        @bottom-center {{
            content: counter(page);
            font-size: 10pt;
            color: #666;
        }}
        @top-center {{
            content: string(book-title);
            font-size: 9pt;
            color: #999;
            font-style: italic;
        }}
    }}
    @page :first {{
        @bottom-center {{
            content: none;
        }}
        @top-center {{
            content: none;
        }}
    }}
    .title-page, .toc-page, .foreword-page, .copyright-page {{
        page: frontmatter;
    }}
    @page frontmatter {{
        @bottom-center {{
            content: counter(page, lower-roman);
            font-size: 10pt;
            color: #666;
        }}
        @top-center {{
            content: none;
        }}
    }}
    body {{
        font-family: Georgia, 'Noto Sans Devanagari', 'Noto Sans Gurmukhi', serif;
        line-height: 1.45;
        font-size: 11pt;
    }}
    h1 {{
        font-size: 20pt;
        margin-top: 1.5em;
        page-break-before: always;
    }}
    h1:first-of-type {{
        page-break-before: avoid;
    }}
    h2 {{
        font-size: 15pt;
        margin-top: 1.2em;
    }}
    .discourse-ref {{
        font-size: 15pt;
        font-weight: bold;
        margin-top: 1.2em;
    }}
    p {{
        margin: 0.7em 0;
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
        string-set: book-title content();
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
    .copyright-page {{
        page-break-after: always;
        text-align: center;
        padding-top: 6cm;
        font-size: 10pt;
        color: #444;
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
    figure.page-image {{
        text-align: center;
        margin: 1em 0;
        page-break-inside: avoid;
    }}
    figure.page-image img {{
        max-width: 90%;
        max-height: 40vh;
    }}
    figure.page-image figcaption {{
        font-size: 9pt;
        font-style: italic;
        color: #555;
        margin-top: 0.3em;
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

    # Deduplicate TOC entries — L1 entries key on (chapter, title, level),
    # L2 sub-entries key on (title, level) only to prevent same discourse
    # reference appearing under multiple chapters
    seen_keys: set[tuple] = set()
    deduped_toc: list[dict] = []
    for toc_entry in table_of_contents:
        level = toc_entry.get("level", 1)
        # Normalize title for dedup
        title_norm = toc_entry.get("title", "").lower().strip()
        if level == 1:
            key = (toc_entry.get("chapter"), title_norm, level)
        else:
            key = (title_norm, level)
        if key not in seen_keys:
            seen_keys.add(key)
            deduped_toc.append(toc_entry)

    parts = ["<div class='toc-page'>\n", "<h1>Table of Contents</h1>\n", "<ul class='toc'>\n"]
    for toc_entry in deduped_toc:
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


def _postprocess_chapter_html(html: str) -> str:
    """Apply export-time fixes to cached manuscript chapter HTML.

    The export script reads pre-built manuscripts from the DB, so fixes
    in the assemble stage don't take effect for already-cached books.
    This function applies text-level corrections at render time.
    """
    import re

    # Clean untranslated passage markers (Issue #77)
    #    Replace "[Original text — translation unavailable]" + raw Hindi
    #    with a clean editorial note. The raw Hindi after the marker may
    #    span multiple lines until the next English paragraph.
    html = re.sub(
        r'\[Original text\s*[—–-]\s*translation unavailable\]'
        r'(?:\s*<[^>]*>)*'   # optional HTML tags
        r'[^<]*?'            # raw Hindi text (non-greedy, within same element)
        r'(?=</)',           # stop before closing tag
        '[A passage from the original text could not be translated and has been omitted.]',
        html,
    )
    # Also handle plain-text version (not wrapped in HTML tags)
    html = re.sub(
        r'\[Original text\s*[—–-]\s*translation unavailable\]'
        r'[\s\S]*?'         # raw source text
        r'(?=</p>|</div>|</em>|\n\n)',
        '[A passage from the original text could not be translated and has been omitted.]',
        html,
    )

    # 3. Strip stray non-Devanagari Indic script (Malayalam, Tamil, etc.)
    #    that leaked through OCR — Issue #79
    html = re.sub(r'[\u0D00-\u0D7F]', '', html)   # Malayalam
    html = re.sub(r'[\u0B80-\u0BFF]', '', html)   # Tamil
    html = re.sub(r'[\u0C00-\u0C7F]', '', html)   # Telugu
    html = re.sub(r'[\u0C80-\u0CFF]', '', html)   # Kannada

    return html


def _build_pdf_body_html(manuscript, glossary):
    """Build the body HTML (foreword + chapters + glossary)."""
    parts = []

    # Translator's Foreword — Issue #12
    foreword_text = manuscript.metadata.get("foreword") if manuscript.metadata else None
    if foreword_text:
        parts.append("<div class='foreword-page'>\n")
        parts.append("<h1>Translator's Foreword</h1>\n")
        parts.append("<div class='foreword-content'>\n")
        for para in foreword_text.split("\n\n"):
            if para.strip():
                parts.append(f"<p>{_escape_html(para.strip())}</p>\n")
        parts.append("</div>\n</div>\n")

    # Reset page counter to arabic 1 at start of body content — Issue #11
    parts.append("<div style='counter-reset: page 1;'></div>\n")

    # Chapters — apply export-time post-processing on cached manuscript HTML
    # Track method numbers to detect gaps and insert editorial notes
    # Track seen h2 headings to deduplicate bookmark generation
    import re as _re
    prev_method = 0
    seen_h2_headings: set[str] = set()
    for chapter in manuscript.chapters:
        html = _postprocess_chapter_html(chapter.content_html)
        # Deduplicate h2 headings across chapters — WeasyPrint generates
        # bookmarks from every h2, so duplicate discourse refs (Pravachan-N)
        # create duplicate bookmarks. Downgrade dupes to <p> elements.
        def _dedup_h2(match):
            heading_text = match.group(2)
            key = heading_text.strip().lower()
            if key in seen_h2_headings:
                # Downgrade to styled paragraph (no bookmark generated)
                return f"<p class='discourse-ref' id='{match.group(1)}'>{heading_text}</p>"
            seen_h2_headings.add(key)
            return match.group(0)
        html = _re.sub(
            r"<h2 id='([^']*)'>(.*?)</h2>",
            _dedup_h2,
            html,
        )
        # Detect method number from chapter title
        method_match = _re.search(r'Method\s+(\d+)', chapter.title)
        if method_match:
            method_num = int(method_match.group(1))
            # Insert editorial note for any skipped methods
            for gap in range(prev_method + 1, method_num):
                parts.append(
                    f"<div class='editorial-note' style='page-break-before: always; "
                    f"padding: 2em; text-align: center; color: #666;'>\n"
                    f"<h1 id='chapter-method-{gap}'>Tantra Sutra — Method {gap}</h1>\n"
                    f"<p><em>[Translator's Note: Method {gap} does not appear in the "
                    f"source edition used for this translation. The original Hindi volume "
                    f"proceeds directly from Method {gap - 1} to Method {gap + 1}.]</em></p>\n"
                    f"</div>\n"
                )
            prev_method = method_num
        parts.append(html)

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
        # Derive subtitle from book title if "Volume" is present
        if not subtitle and hasattr(manuscript, '_book_title'):
            import re
            vol_match = re.search(r'(Volume\s+\d+|Part\s+\d+|भाग[\s-]*\d+)', manuscript._book_title, re.IGNORECASE)
            if vol_match:
                subtitle = vol_match.group(1)
        parts.append("<div class='title-page'>\n")
        parts.append(f"<div class='title'>{_escape_html(manuscript.title)}</div>\n")
        if subtitle:
            parts.append(f"<div class='subtitle'>{_escape_html(subtitle)}</div>\n")
        parts.append("<hr class='title-separator'>\n")
        if manuscript.author:
            parts.append(f"<div class='author'>{_escape_html(manuscript.author)}</div>\n")
        parts.append("</div>\n")

    # Copyright / attribution page
    parts.append("<div class='copyright-page'>\n")
    author_name = manuscript.author or "Unknown"
    parts.append(f"<p><strong>{_escape_html(manuscript.title)}</strong></p>\n")
    parts.append(f"<p>by {_escape_html(author_name)}</p>\n")
    parts.append("<br/>\n")
    parts.append(f"<p>&copy; {_escape_html(author_name)} Foundation International</p>\n")
    parts.append("<p>English translation produced by Transpose AI Translation Pipeline</p>\n")
    parts.append("<br/>\n")
    parts.append("<p><em>All rights reserved. No part of this publication may be reproduced, "
                 "stored in a retrieval system, or transmitted in any form or by any means "
                 "without the prior written permission of the copyright holder.</em></p>\n")
    parts.append("<br/>\n")
    parts.append("<p>Cultural terms from the original language have been preserved "
                 "to maintain authenticity. A glossary is provided at the end of this volume.</p>\n")
    parts.append("</div>\n")

    # ToC
    parts.append(toc_html)

    # Body (foreword + chapters + glossary)
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

    # Count front-matter pages (title, ToC, foreword — before body content)
    frontmatter_pages = 0
    body_started = False
    # Match Chapter N:, Tantra Sutra — Method N, or Method N (Issue #68)
    chapter_pattern = re.compile(
        r"(Chapter\s+(\d+)\s*:|Tantra\s+Sutra\s*[—\u2014\u2013-]\s*Method\s*(\d+)|Method\s+(\d+))",
        re.IGNORECASE,
    )

    page_map = {}
    chapter_counter = 0
    for page_idx in range(doc.page_count):
        text = doc[page_idx].get_text()

        # Detect first chapter heading = start of body
        match = chapter_pattern.search(text)
        if match and not body_started:
            body_started = True
            frontmatter_pages = page_idx

        if match:
            chapter_counter += 1
            # Use Chapter N number if available, else sequential counter
            chapter_num = int(match.group(2) or match.group(3) or match.group(4) or chapter_counter)
            body_page = page_idx - frontmatter_pages + 1
            page_map[chapter_counter] = body_page

    doc.close()
    return page_map


async def _resolve_chapter_images(manuscript, ctx, logger) -> None:
    """Download blob-hosted images in chapter HTML and replace with base64 data URIs.

    This ensures WeasyPrint and ePub can embed the images without network access.
    Modifies manuscript.chapters in-place.
    """
    import base64
    import re

    blob_img_re = re.compile(r"<img src='([^']+blob[^']+)' alt='([^']*)'/>")

    for chapter in manuscript.chapters:
        matches = blob_img_re.findall(chapter.content_html)
        if not matches:
            continue

        for blob_uri, alt_text in matches:
            try:
                blob_name = blob_uri.split("/")[-1]
                img_data = await ctx.blob.download_blob(
                    container=ctx.settings.blob_container_source,
                    blob_name=blob_name,
                )
                b64 = base64.b64encode(img_data).decode("ascii")
                data_uri = f"data:image/png;base64,{b64}"
                chapter.content_html = chapter.content_html.replace(blob_uri, data_uri)
                logger.debug("Resolved image %s (%d bytes)", blob_name, len(img_data))
            except Exception:
                logger.warning("Could not resolve image: %s", blob_uri, exc_info=True)
                # Remove the broken image tag
                chapter.content_html = chapter.content_html.replace(
                    f"<figure class='page-image'><img src='{blob_uri}' alt='{alt_text}'/></figure>\n",
                    "",
                )


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


def _set_pdf_metadata(pdf_bytes: bytes, manuscript, book) -> bytes:
    """Set PDF metadata (title, author, subject, keywords) via PyMuPDF."""
    try:
        import fitz
    except ImportError:
        return pdf_bytes

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        metadata = doc.metadata or {}
        metadata["title"] = book.title or manuscript.title
        metadata["author"] = manuscript.author or book.author or ""
        metadata["subject"] = "Spiritual / Meditation — English translation"
        metadata["keywords"] = "tantra, meditation, osho, vigyan bhairav tantra, translation"
        metadata["creator"] = "Transpose AI Translation Pipeline"
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).strftime("D:%Y%m%d%H%M%S+00'00'")
        metadata["creationDate"] = now
        metadata["modDate"] = now
        doc.set_metadata(metadata)
        out_bytes = doc.tobytes()
        doc.close()
        return out_bytes
    except Exception:
        return pdf_bytes

