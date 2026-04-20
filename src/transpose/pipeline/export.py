"""Stage 7: Export — ePub and PDF rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

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

    artifacts: list[ExportArtifact] = []

    # Generate ePub if requested
    if "epub" in input.formats:
        epub_data = await _generate_epub(manuscript, glossary, book)
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
        pdf_data = await _generate_pdf(manuscript, glossary, book)
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


async def _generate_epub(manuscript, glossary, book) -> bytes:
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

    # Cover page as first chapter — Issue #10
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

    # Add Translator's Foreword if present
    epub_chapters = [cover_page]
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


async def _generate_pdf(manuscript, glossary, book) -> bytes:
    """Generate PDF file from manuscript HTML."""
    from pathlib import Path

    from weasyprint import CSS, HTML
    from weasyprint.text.fonts import FontConfiguration

    # Resolve font path relative to repo root
    font_path = Path(__file__).resolve().parents[3] / "fonts" / "NotoSansDevanagari.ttf"

    # FontConfiguration must be shared between CSS parsing and PDF rendering
    # so that @font-face declarations (especially for complex scripts like
    # Devanagari which need GSUB/GPOS tables) are processed correctly.
    font_config = FontConfiguration()

    stylesheet = CSS(
        string=f"""
        @font-face {{
            font-family: 'Noto Sans Devanagari';
            src: url('file://{font_path}') format('truetype');
            font-weight: normal;
            font-style: normal;
        }}
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
            font-family: Georgia, 'Noto Sans Devanagari', serif;
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
            content: target-counter(attr(href url), page);
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
        """,
        font_config=font_config,
    )

    # Build HTML document (no inline styles — handled by stylesheet above)
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"></head>
    <body>
    """

    # Title page (cover) — Issue #10
    subtitle = (manuscript.metadata or {}).get("subtitle", "")
    html_content += "<div class='title-page'>\n"
    html_content += f"<div class='title'>{_escape_html(manuscript.title)}</div>\n"
    if subtitle:
        html_content += f"<div class='subtitle'>{_escape_html(subtitle)}</div>\n"
    html_content += "<hr class='title-separator'>\n"
    if manuscript.author:
        html_content += f"<div class='author'>{_escape_html(manuscript.author)}</div>\n"
    html_content += "</div>\n"

    # Table of Contents page — Issue #13
    if manuscript.table_of_contents:
        html_content += "<div class='toc-page'>\n"
        html_content += "<h1>Table of Contents</h1>\n"
        html_content += "<ul class='toc'>\n"
        for toc_entry in manuscript.table_of_contents:
            chapter_num = toc_entry.get('chapter', '')
            chapter_id = f"chapter-{chapter_num}"
            html_content += "<li class='toc-entry'>"
            html_content += f"<a href='#{chapter_id}'>"
            html_content += f"<span class='toc-title'>{_escape_html(toc_entry['title'])}</span>"
            html_content += "</a>"
            html_content += "</li>\n"
        html_content += "</ul>\n"
        html_content += "</div>\n"

    # Translator's Foreword — Issue #12
    foreword_text = manuscript.metadata.get("foreword") if manuscript.metadata else None
    if foreword_text:
        html_content += "<div class='foreword-page'>\n"
        html_content += "<h1>Translator's Foreword</h1>\n"
        html_content += "<div class='foreword-content'>\n"
        for para in foreword_text.split("\n\n"):
            if para.strip():
                html_content += f"<p>{_escape_html(para.strip())}</p>\n"
        html_content += "</div>\n</div>\n"

    # Reset page counter to arabic 1 at start of body content — Issue #11
    html_content += "<div style='counter-reset: page 1;'></div>\n"

    # Chapters
    for chapter in manuscript.chapters:
        html_content += chapter.content_html

    # Glossary
    if glossary and glossary.entries:
        html_content += "<h1>Glossary</h1>\n<dl>\n"
        for entry in sorted(glossary.entries, key=lambda e: e.term):
            html_content += f"<dt class='glossary-term'>{_escape_html(entry.term)}"
            if entry.original_script:
                html_content += f" ({_escape_html(normalize_unicode(entry.original_script))})"
            html_content += f"</dt>\n<dd>{_escape_html(entry.definition)}</dd>\n"
        html_content += "</dl>\n"

    html_content += "</body></html>"

    pdf_bytes = HTML(string=html_content).write_pdf(
        stylesheets=[stylesheet],
        font_config=font_config,
    )
    return pdf_bytes


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


def _escape_html(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

