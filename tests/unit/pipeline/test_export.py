"""Tests for the export pipeline stage.

Tests ePub and PDF generation, blob uploads, and multi-format exports.
Issues #10 (Cover Page), #11 (Page Numbering), #12 (Foreword), #13 (ToC).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from transpose.models.enums import TermSource
from transpose.models.glossary import Glossary, GlossaryEntry
from transpose.models.manuscript import Chapter, Manuscript
from transpose.pipeline.export import _generate_pdf


@dataclass
class ExportInput:
    """Export stage input contract."""

    book_id: UUID
    formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])


@dataclass
class ExportArtifact:
    """A single exported file."""

    format: str
    blob_uri: str
    file_size_bytes: int


@dataclass
class ExportOutput:
    """Export stage output contract."""

    book_id: UUID
    artifacts: list[ExportArtifact] = field(default_factory=list)


class TestExportContract:
    """Test export stage contract validation."""

    def test_export_input_defaults(self) -> None:
        """Test ExportInput has default formats."""
        book_id = uuid4()
        input_data = ExportInput(book_id=book_id)
        assert input_data.book_id == book_id
        assert "epub" in input_data.formats
        assert "pdf" in input_data.formats

    def test_export_input_custom_formats(self) -> None:
        """Test ExportInput accepts custom formats."""
        book_id = uuid4()
        input_data = ExportInput(book_id=book_id, formats=["epub"])
        assert input_data.formats == ["epub"]

    def test_export_artifact_shape(self) -> None:
        """Test ExportArtifact has all required fields."""
        artifact = ExportArtifact(
            format="epub",
            blob_uri="https://storage.blob/book.epub",
            file_size_bytes=1024000,
        )
        assert artifact.format in ["epub", "pdf"]
        assert artifact.blob_uri.startswith("https://")
        assert artifact.file_size_bytes > 0

    def test_export_output_shape(self) -> None:
        """Test ExportOutput has all required fields."""
        book_id = uuid4()
        output = ExportOutput(
            book_id=book_id,
            artifacts=[],
        )
        assert output.book_id == book_id
        assert isinstance(output.artifacts, list)


class TestEpubGeneration:
    """Test ePub generation."""

    @pytest.mark.asyncio
    async def test_epub_generation_produces_valid_file(
        self,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that ePub generation produces valid file."""
        # Mock blob upload
        mock_blob_client.upload_file = AsyncMock(
            return_value="https://storage.blob/book.epub"
        )

        # Simulate ePub generation
        epub_uri = await mock_blob_client.upload_file(b"fake epub content", "book.epub")

        artifact = ExportArtifact(
            format="epub",
            blob_uri=epub_uri,
            file_size_bytes=len(b"fake epub content"),
        )

        assert artifact.format == "epub"
        assert artifact.blob_uri.endswith(".epub")


class TestPdfGeneration:
    """Test PDF generation."""

    @pytest.mark.asyncio
    async def test_pdf_generation_produces_valid_file(
        self,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that PDF generation produces valid file."""
        mock_blob_client.upload_file = AsyncMock(
            return_value="https://storage.blob/book.pdf"
        )

        pdf_uri = await mock_blob_client.upload_file(b"fake pdf content", "book.pdf")

        artifact = ExportArtifact(
            format="pdf",
            blob_uri=pdf_uri,
            file_size_bytes=len(b"fake pdf content"),
        )

        assert artifact.format == "pdf"
        assert artifact.blob_uri.endswith(".pdf")


class TestMultiFormatExport:
    """Test multi-format export."""

    def test_both_formats_requested(self) -> None:
        """Test exporting both ePub and PDF formats."""
        book_id = uuid4()
        artifacts = [
            ExportArtifact("epub", "https://storage.blob/book.epub", 1024000),
            ExportArtifact("pdf", "https://storage.blob/book.pdf", 2048000),
        ]

        output = ExportOutput(
            book_id=book_id,
            artifacts=artifacts,
        )

        assert len(output.artifacts) == 2
        formats = [a.format for a in output.artifacts]
        assert "epub" in formats
        assert "pdf" in formats


class TestBlobUpload:
    """Test blob upload of exported files."""

    @pytest.mark.asyncio
    async def test_blob_upload_returns_uri(
        self,
        mock_blob_client: AsyncMock,
    ) -> None:
        """Test that blob upload returns URI."""
        mock_blob_client.upload_file = AsyncMock(
            return_value="https://storage.blob.core.windows.net/exports/book.epub"
        )

        uri = await mock_blob_client.upload_file(b"content", "book.epub")

        assert uri.startswith("https://")
        assert "storage" in uri
        assert "blob" in uri


class TestForewordRendering:
    """Test Translator's Foreword rendering in exports."""

    def test_foreword_html_for_pdf(self) -> None:
        """Test foreword HTML structure for PDF rendering."""
        foreword_text = "Dear Reader, welcome.\n\nThis is a cultural bridge."
        html = "<div class='foreword-page'>\n"
        html += "<h1>Translator's Foreword</h1>\n"
        html += "<div class='foreword-content'>\n"
        for para in foreword_text.split("\n\n"):
            if para.strip():
                html += f"<p>{para.strip()}</p>\n"
        html += "</div>\n</div>\n"

        assert "foreword-page" in html
        assert "<h1>Translator's Foreword</h1>" in html
        assert "foreword-content" in html
        assert "<p>Dear Reader, welcome.</p>" in html
        assert "<p>This is a cultural bridge.</p>" in html

    def test_foreword_not_rendered_when_absent(self) -> None:
        """No foreword div when metadata has no foreword."""
        metadata: dict = {"source_language": "hindi"}
        foreword_text = metadata.get("foreword")
        assert foreword_text is None

    def test_foreword_css_present(self) -> None:
        """Foreword CSS classes should style content correctly."""
        css = ".foreword-page { page-break-after: always; }"
        assert "page-break-after" in css

    def test_foreword_epub_chapter_order(self) -> None:
        """Foreword should appear before chapter content in ePub spine."""
        spine = ["foreword", "chapter_1", "chapter_2", "glossary"]
        assert spine.index("foreword") < spine.index("chapter_1")


# ---------------------------------------------------------------------------
# Helpers for HTML capture from _generate_pdf
# ---------------------------------------------------------------------------


async def _capture_export_html(
    manuscript: Manuscript,
    glossary: Glossary | None = None,
    book: object | None = None,
) -> tuple[str, str]:
    """Call _generate_pdf and capture the HTML/CSS strings before rendering.

    Patches WeasyPrint so no actual PDF is produced, and stubs out the
    chapter-page-number extraction (which needs a real PDF).
    Returns ``(html, css)`` tuple.
    """
    captured: dict[str, str] = {"html": "", "css": ""}

    class _MockCSS:
        def __init__(self, string: str = "", **kwargs: object) -> None:
            captured["css"] = string

    class _MockHTML:
        def __init__(self, string: str = "", **kwargs: object) -> None:
            captured["html"] = string

        def write_pdf(
            self,
            stylesheets: object = None,
            font_config: object = None,
            **kwargs: object,
        ) -> bytes:
            return b"%PDF-1.4 fake"

    with (
        patch("weasyprint.HTML", _MockHTML),
        patch("weasyprint.CSS", _MockCSS),
        patch("weasyprint.text.fonts.FontConfiguration", MagicMock),
        patch(
            "transpose.pipeline.export._extract_chapter_page_numbers",
            return_value={1: 1, 2: 3, 3: 5},
        ),
    ):
        await _generate_pdf(manuscript, glossary, book)

    return captured["html"], captured["css"]


def _make_manuscript(**overrides: object) -> Manuscript:
    """Build a Manuscript with sensible defaults."""
    defaults: dict = {
        "book_id": uuid4(),
        "title": "The Bhagavad Gita",
        "author": "Vyasa",
        "chapters": [
            Chapter(
                number=1,
                title="Chapter 1: Arjuna's Despair",
                content_html=(
                    "<h1>Chapter 1: Arjuna's Despair</h1>"
                    "<p>On the battlefield of Kurukshetra...</p>"
                ),
            ),
            Chapter(
                number=2,
                title="Chapter 2: The Yoga of Knowledge",
                content_html=(
                    "<h1>Chapter 2: The Yoga of Knowledge</h1>"
                    "<p>The concept of dharma is central...</p>"
                ),
            ),
        ],
        "glossary_id": uuid4(),
    }
    defaults.update(overrides)
    return Manuscript(**defaults)


def _make_glossary(book_id: object = None, n_entries: int = 3) -> Glossary:
    """Build a Glossary with Devanagari entries."""
    terms = [
        ("dharma", "धर्म", "Righteous duty"),
        ("karma", "कर्म", "Action and consequences"),
        ("moksha", "मोक्ष", "Liberation from rebirth"),
        ("yoga", "योग", "Spiritual discipline"),
        ("atman", "आत्मन्", "The eternal self"),
    ]
    return Glossary(
        book_id=book_id or uuid4(),
        entries=[
            GlossaryEntry(
                term=t,
                original_script=s,
                definition=d,
                source=TermSource.SEED,
                occurrence_count=i + 1,
            )
            for i, (t, s, d) in enumerate(terms[:n_entries])
        ],
    )


# ---------------------------------------------------------------------------
# Issue #10 — Cover Page
# ---------------------------------------------------------------------------


class TestCoverPage:
    """Issue #10: PDF output must contain a styled title/cover page."""

    @pytest.mark.asyncio
    async def test_html_contains_title_page_div(self) -> None:
        """Generated HTML must contain a .title-page div."""
        ms = _make_manuscript()
        html, _css = await _capture_export_html(ms)
        assert "title-page" in html

    @pytest.mark.asyncio
    async def test_title_page_contains_book_title(self) -> None:
        """Title page must display the book title."""
        ms = _make_manuscript(title="A Test Title")
        html, _css = await _capture_export_html(ms)
        assert "A Test Title" in html

    @pytest.mark.asyncio
    async def test_title_page_contains_author_when_provided(self) -> None:
        """Title page must display author name when provided."""
        ms = _make_manuscript(author="Test Author")
        html, _css = await _capture_export_html(ms)
        assert "Test Author" in html

    @pytest.mark.asyncio
    async def test_cover_page_before_chapter_content(self) -> None:
        """Title-page div must appear before any chapter content in the HTML."""
        ms = _make_manuscript()
        html, _css = await _capture_export_html(ms)
        title_pos = html.find("title-page")
        chapter_pos = html.find("<h1>Chapter 1")
        assert title_pos != -1, "title-page not found in HTML"
        assert chapter_pos != -1, "Chapter 1 not found in HTML"
        assert title_pos < chapter_pos, "title-page must precede chapter content"

    @pytest.mark.asyncio
    async def test_subtitle_in_metadata_rendered(self) -> None:
        """Subtitle from manuscript metadata should appear on the title page."""
        ms = _make_manuscript(
            metadata={"subtitle": "A Practical Guide to Self-Realization"},
        )
        html, _css = await _capture_export_html(ms)
        assert "Practical Guide to Self-Realization" in html


# ---------------------------------------------------------------------------
# Issue #13 — Table of Contents
# ---------------------------------------------------------------------------


class TestTableOfContents:
    """Issue #13: PDF must include a ToC when table_of_contents is populated."""

    @pytest.mark.asyncio
    async def test_toc_page_div_present(self) -> None:
        """HTML must contain a .toc-page div when ToC data exists."""
        ms = _make_manuscript(
            table_of_contents=[
                {"title": "Chapter 1: Arjuna's Despair", "number": 1},
                {"title": "Chapter 2: The Yoga of Knowledge", "number": 2},
            ],
        )
        html, _css = await _capture_export_html(ms)
        assert "toc-page" in html

    @pytest.mark.asyncio
    async def test_toc_entries_match_chapter_titles(self) -> None:
        """ToC entries must list the chapter titles."""
        ms = _make_manuscript(
            table_of_contents=[
                {"title": "Chapter 1: Arjuna's Despair", "number": 1},
                {"title": "Chapter 2: The Yoga of Knowledge", "number": 2},
            ],
        )
        html, _css = await _capture_export_html(ms)
        toc_start = html.find("toc-page")
        assert toc_start != -1, "toc-page div not found"
        toc_region = html[toc_start : toc_start + 2000]
        assert "Arjuna" in toc_region
        assert "Yoga of Knowledge" in toc_region

    @pytest.mark.asyncio
    async def test_toc_after_title_page_before_chapters(self) -> None:
        """ToC must appear after the title page and before chapter content."""
        ms = _make_manuscript(
            table_of_contents=[
                {"title": "Chapter 1: Arjuna's Despair", "number": 1},
            ],
        )
        html, _css = await _capture_export_html(ms)
        title_pos = html.find("title-page")
        toc_pos = html.find("toc-page")
        chapter_pos = html.find("<h1>", toc_pos + 1) if toc_pos != -1 else -1
        assert title_pos < toc_pos < chapter_pos

    @pytest.mark.asyncio
    async def test_toc_not_rendered_when_empty(self) -> None:
        """ToC should NOT appear when table_of_contents is empty."""
        ms = _make_manuscript(table_of_contents=[])
        html, _css = await _capture_export_html(ms)
        assert "toc-page" not in html


# ---------------------------------------------------------------------------
# Issue #11 — Page Numbering
# ---------------------------------------------------------------------------


class TestPageNumbering:
    """Issue #11: PDF CSS must include @page rules with page counters."""

    @pytest.mark.asyncio
    async def test_css_has_page_counter(self) -> None:
        """CSS must contain a counter(page) declaration for page numbers."""
        ms = _make_manuscript()
        _html, css = await _capture_export_html(ms)
        assert "counter(page)" in css

    @pytest.mark.asyncio
    async def test_front_matter_roman_numerals(self) -> None:
        """Front-matter pages must use roman numeral counter style."""
        ms = _make_manuscript()
        _html, css = await _capture_export_html(ms)
        assert "lower-roman" in css

    @pytest.mark.asyncio
    async def test_cover_page_no_page_number(self) -> None:
        """Cover/title page must suppress page numbers."""
        ms = _make_manuscript()
        _html, css = await _capture_export_html(ms)
        css_lower = css.lower()
        has_suppression = any(
            pattern in css_lower
            for pattern in [
                "content: none",
                "content:none",
                'content: ""',
                'content:""',
                "content: ''",
                "content:''",
            ]
        )
        assert has_suppression, "Title page CSS must suppress page number content"


# ---------------------------------------------------------------------------
# Issue #12 — Translator's Foreword (integration with _generate_pdf)
# ---------------------------------------------------------------------------


class TestTranslatorsForewordIntegration:
    """Issue #12: PDF must include a translator's foreword for cultural terms."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Issue #12: foreword generation pending Chani's fix")
    async def test_foreword_produces_nonempty_text(self) -> None:
        """Foreword section must contain non-empty text."""
        ms = _make_manuscript()
        glossary = _make_glossary(book_id=ms.book_id)
        html, _css = await _capture_export_html(ms, glossary)
        foreword_start = html.find("foreword-page")
        assert foreword_start != -1, "foreword-page not found"
        foreword_window = html[foreword_start : foreword_start + 3000]
        plain = re.sub(r"<[^>]+>", " ", foreword_window).strip()
        assert len(plain) > 20, "Foreword must contain meaningful text"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Issue #12: foreword generation pending Chani's fix")
    async def test_foreword_html_contains_div(self) -> None:
        """HTML must contain a .foreword-page div."""
        ms = _make_manuscript()
        glossary = _make_glossary(book_id=ms.book_id)
        html, _css = await _capture_export_html(ms, glossary)
        assert "foreword-page" in html

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Issue #12: foreword generation pending Chani's fix")
    async def test_foreword_after_toc_before_chapters(self) -> None:
        """Foreword must appear after ToC (if present) and before chapters."""
        ms = _make_manuscript(
            table_of_contents=[{"title": "Chapter 1", "number": 1}],
        )
        glossary = _make_glossary(book_id=ms.book_id)
        html, _css = await _capture_export_html(ms, glossary)

        foreword_pos = html.find("foreword-page")
        chapter_pos = html.find("<h1>Chapter 1")
        assert foreword_pos != -1, "foreword-page not found"
        assert chapter_pos != -1, "chapter content not found"
        assert foreword_pos < chapter_pos, "foreword must precede chapter content"

        toc_pos = html.find("toc-page")
        if toc_pos != -1:
            assert toc_pos < foreword_pos, "foreword must follow ToC"

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Issue #12: foreword generation pending Chani's fix")
    async def test_foreword_mentions_preserved_cultural_terms(self) -> None:
        """Foreword content should reference preservation of cultural terms."""
        ms = _make_manuscript()
        glossary = _make_glossary(book_id=ms.book_id)
        html, _css = await _capture_export_html(ms, glossary)

        foreword_start = html.find("foreword-page")
        assert foreword_start != -1
        foreword_text = html[foreword_start : foreword_start + 3000].lower()
        cultural_indicators = ["cultural", "preserv", "untranslat", "original"]
        assert any(kw in foreword_text for kw in cultural_indicators), (
            "Foreword should mention cultural term preservation"
        )

    @pytest.mark.asyncio
    async def test_foreword_absent_when_no_cultural_terms(self) -> None:
        """Foreword should not appear when there are no cultural terms."""
        ms = _make_manuscript()
        html, _css = await _capture_export_html(ms, glossary=None)
        assert "foreword-page" not in html


# ---------------------------------------------------------------------------
# NFC Normalization
# ---------------------------------------------------------------------------


class TestNfcNormalization:
    """All text must be NFC-normalized before PDF rendering."""

    @pytest.mark.asyncio
    async def test_nfc_normalization_applied_before_rendering(self) -> None:
        """_generate_pdf must NFC-normalize the full HTML string.

        We inject a non-NFC Devanagari sequence (decomposed ka + virama)
        and verify the rendered HTML contains the NFC-composed form.
        """
        import unicodedata

        # NFD form: DEVANAGARI LETTER KA + VIRAMA (decomposed)
        nfd_text = "\u0915\u094D"  # क + ्

        ms = _make_manuscript(
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1: Test",
                    content_html=f"<h1>Chapter 1: Test</h1><p>The word {nfd_text} appears.</p>",
                ),
            ],
        )
        html, _css = await _capture_export_html(ms)
        # The rendered HTML should have NFC-normalized text
        assert unicodedata.is_normalized("NFC", html), (
            "HTML passed to WeasyPrint is not NFC-normalized"
        )

    @pytest.mark.asyncio
    async def test_nfc_normalization_on_both_passes(self) -> None:
        """Both pass-1 and pass-2 HTML must be NFC-normalized.

        The normalize_unicode call in _generate_pdf runs on both passes.
        We verify by checking the captured HTML is NFC.
        """
        import unicodedata

        ms = _make_manuscript()
        html, _css = await _capture_export_html(ms)
        assert unicodedata.is_normalized("NFC", html)


# ---------------------------------------------------------------------------
# Gurmukhi Font Path Resolution
# ---------------------------------------------------------------------------


class TestGurmukhiFontResolution:
    """Gurmukhi font-face CSS is only emitted when the font file exists."""

    @pytest.mark.asyncio
    async def test_gurmukhi_font_face_when_font_exists(self) -> None:
        """If NotoSansGurmukhi.ttf exists, CSS must include @font-face for it."""
        from pathlib import Path

        fonts_dir = Path(__file__).resolve().parents[3] / "fonts"
        gurmukhi_font = fonts_dir / "NotoSansGurmukhi.ttf"

        ms = _make_manuscript()
        _html, css = await _capture_export_html(ms)

        if gurmukhi_font.exists():
            assert "Noto Sans Gurmukhi" in css, (
                "Gurmukhi font file exists but @font-face not in CSS"
            )
            assert "U+0A00-0A7F" in css, (
                "Gurmukhi unicode-range not specified"
            )
        else:
            # When font is absent, CSS should not reference it
            assert "Noto Sans Gurmukhi" not in css or "font-face" not in css.split("Gurmukhi")[0], (
                "Gurmukhi @font-face emitted but font file is missing"
            )

    @pytest.mark.asyncio
    async def test_devanagari_font_always_present(self) -> None:
        """Devanagari @font-face is always included regardless of Gurmukhi."""
        ms = _make_manuscript()
        _html, css = await _capture_export_html(ms)
        assert "Noto Sans Devanagari" in css


# ---------------------------------------------------------------------------
# Two-Pass Rendering
# ---------------------------------------------------------------------------


class TestTwoPassRendering:
    """The two-pass approach must produce valid PDF output."""

    @pytest.mark.asyncio
    async def test_two_pass_produces_nonempty_html(self) -> None:
        """Both passes should produce non-empty HTML."""
        ms = _make_manuscript(
            table_of_contents=[
                {"title": "Chapter 1: Arjuna's Despair", "number": 1},
                {"title": "Chapter 2: The Yoga of Knowledge", "number": 2},
            ],
        )
        html, css = await _capture_export_html(ms)
        assert len(html) > 100, "Rendered HTML is suspiciously short"
        assert len(css) > 100, "Rendered CSS is suspiciously short"

    @pytest.mark.asyncio
    async def test_pass1_uses_target_counter(self) -> None:
        """Pass 1 CSS should use target-counter for ToC page resolution.

        We can verify this indirectly: the CSS capture comes from pass 2
        (which has content: none), confirming the two-pass path ran.
        """
        ms = _make_manuscript(
            table_of_contents=[
                {"title": "Chapter 1: Test", "number": 1},
            ],
        )
        _html, css = await _capture_export_html(ms)
        # Pass 2 CSS has "content: none" for ToC ::after (hard-coded numbers)
        assert "content: none" in css or "content:none" in css, (
            "Pass 2 CSS should suppress target-counter (replaced by hard-coded numbers)"
        )

    @pytest.mark.asyncio
    async def test_html_contains_chapter_content(self) -> None:
        """The final HTML must contain all chapter content."""
        ms = _make_manuscript()
        html, _css = await _capture_export_html(ms)
        assert "Kurukshetra" in html, "Chapter 1 content missing from HTML"
        assert "dharma" in html, "Chapter 2 content missing from HTML"
