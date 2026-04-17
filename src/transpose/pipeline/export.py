"""Stage 7: Export — ePub and PDF rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


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
    """
    nav_css = epub.EpubItem(
        uid="style_nav",
        file_name="style/nav.css",
        media_type="text/css",
        content=css,
    )
    ebook.add_item(nav_css)

    # Add chapters
    epub_chapters = []
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
                glossary_html += f" ({entry.original_script})"
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
    from weasyprint import HTML

    # Build complete HTML document
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {
                size: A4;
                margin: 2.5cm;
            }
            body {
                font-family: Georgia, serif;
                line-height: 1.6;
                font-size: 12pt;
            }
            h1 {
                font-size: 24pt;
                margin-top: 2em;
                page-break-before: always;
            }
            h1:first-of-type {
                page-break-before: avoid;
            }
            h2 {
                font-size: 18pt;
                margin-top: 1.5em;
            }
            p {
                margin: 1em 0;
                text-align: justify;
            }
            .title-page {
                text-align: center;
                padding-top: 5cm;
            }
            .title {
                font-size: 36pt;
                font-weight: bold;
            }
            .author {
                font-size: 18pt;
                margin-top: 2em;
            }
            .glossary-term {
                font-weight: bold;
            }
            dl {
                margin: 1em 0;
            }
            dt {
                font-weight: bold;
                margin-top: 0.5em;
            }
            dd {
                margin-left: 2em;
            }
        </style>
    </head>
    <body>
    """

    # Title page
    html_content += "<div class='title-page'>\n"
    html_content += f"<div class='title'>{_escape_html(manuscript.title)}</div>\n"
    if manuscript.author:
        html_content += f"<div class='author'>{_escape_html(manuscript.author)}</div>\n"
    html_content += "</div>\n"

    # Chapters
    for chapter in manuscript.chapters:
        html_content += chapter.content_html

    # Glossary
    if glossary and glossary.entries:
        html_content += "<h1>Glossary</h1>\n<dl>\n"
        for entry in sorted(glossary.entries, key=lambda e: e.term):
            html_content += f"<dt class='glossary-term'>{_escape_html(entry.term)}"
            if entry.original_script:
                html_content += f" ({_escape_html(entry.original_script)})"
            html_content += f"</dt>\n<dd>{_escape_html(entry.definition)}</dd>\n"
        html_content += "</dl>\n"

    html_content += "</body></html>"

    # Generate PDF
    pdf_bytes = HTML(string=html_content).write_pdf()
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

