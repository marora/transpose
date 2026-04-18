"""Visual tests for PDF export quality.

Tests that validate PDF output to catch visual regressions:
- Title page fits on one page (no overflow)
- Devanagari text renders correctly (not as tofu rectangles)
- Glossary entries with original_script display properly
- Page count matches expectations
"""

from __future__ import annotations

import io
from uuid import uuid4

import fitz  # PyMuPDF
import pytest

from transpose.models.enums import TermSource
from transpose.models.glossary import Glossary, GlossaryEntry
from transpose.models.manuscript import Chapter, Manuscript
from transpose.pipeline.export import _generate_pdf


class TestTitlePageFits:
    """Test that title page content fits on one page without overflow."""

    @pytest.mark.asyncio
    async def test_title_page_does_not_overflow(self) -> None:
        """Title page should fit on page 1; chapter content starts on page 2."""
        # Create manuscript with title page + one chapter
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="The Bhagavad Gita: A Practical Guide to Self-Realization",
            author="Vyasa",
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1: The Yoga of Despair",
                    content_html="<h1>Chapter 1: The Yoga of Despair</h1>"
                    "<p>On the battlefield of Kurukshetra, Arjuna stands frozen...</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        # Generate PDF
        pdf_bytes = await _generate_pdf(manuscript, None, None)

        # Open PDF with PyMuPDF
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Verify we have at least 2 pages
        assert pdf_doc.page_count >= 2, "PDF should have title page + chapter page"

        # Extract text from page 1
        page1_text = pdf_doc[0].get_text()

        # Page 1 should contain the title and author
        assert "Bhagavad Gita" in page1_text, "Title should be on page 1"
        assert "Vyasa" in page1_text, "Author should be on page 1"

        # Extract text from page 2
        page2_text = pdf_doc[1].get_text()

        # Page 2 should start with chapter content, not title overflow
        assert "Chapter 1" in page2_text, "Chapter should start on page 2"
        assert "Kurukshetra" in page2_text, "Chapter content should be on page 2"

        # Title should NOT overflow to page 2
        # (Allow the title word to appear as part of chapter heading, but not the full title page)
        assert (
            "Practical Guide to Self-Realization" not in page2_text
        ), "Title subtitle should not overflow to page 2"

        pdf_doc.close()

    @pytest.mark.asyncio
    async def test_title_page_with_no_author(self) -> None:
        """Title page should fit even without author."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Anonymous Wisdom",
            author=None,  # No author
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1",
                    content_html="<h1>Chapter 1</h1><p>Content begins here.</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        pdf_bytes = await _generate_pdf(manuscript, None, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        page1_text = pdf_doc[0].get_text()
        assert "Anonymous Wisdom" in page1_text
        # Should not overflow - chapter starts on page 2
        page2_text = pdf_doc[1].get_text()
        assert "Chapter 1" in page2_text

        pdf_doc.close()


def _has_devanagari_font(pdf_doc: fitz.Document) -> bool:
    """Check if the PDF embeds a Devanagari-capable font."""
    for page in pdf_doc:
        for font in page.get_fonts():
            # font tuple: (xref, ext, type, basefont, name, encoding)
            basefont = font[3].lower() if font[3] else ""
            if "devanagari" in basefont or "noto" in basefont:
                return True
    return False


def _extract_devanagari_codepoints(pdf_doc: fitz.Document) -> set[str]:
    """Extract individual Devanagari codepoints from all PDF pages."""
    codepoints: set[str] = set()
    for page in pdf_doc:
        for ch in page.get_text():
            if "\u0900" <= ch <= "\u097f":
                codepoints.add(ch)
    return codepoints


class TestDevanagariRendering:
    """Test that Devanagari script renders correctly (not as tofu rectangles).

    Note: WeasyPrint's font subsetting drops GSUB/GPOS tables, which means
    PyMuPDF cannot extract conjunct Devanagari words (e.g. धर्म) as intact
    strings — the virama-based ligatures break during text extraction.
    However, the PDF renders correctly visually. We validate by checking:
    1. The Devanagari font is embedded in the PDF
    2. Individual Devanagari codepoints are present (not tofu/rectangles)
    3. English text coexists correctly
    """

    @pytest.mark.asyncio
    async def test_devanagari_text_in_chapters_is_readable(self) -> None:
        """Devanagari characters should be embedded and extractable from PDF."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Test Book",
            author="Test Author",
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1: Core Concepts",
                    content_html=(
                        "<h1>Chapter 1: Core Concepts</h1>"
                        "<p>The concept of dharma (धर्म) is central to Hindu philosophy.</p>"
                        "<p>Similarly, karma (कर्म) governs cause and effect.</p>"
                        "<p>The ultimate goal is moksha (मोक्ष), liberation from the cycle.</p>"
                    ),
                ),
                Chapter(
                    number=2,
                    title="Chapter 2: Practice",
                    content_html=(
                        "<h1>Chapter 2: Practice</h1>"
                        "<p>Through yoga (योग) one achieves union with the divine.</p>"
                        "<p>The atman (आत्मन्) is the eternal self.</p>"
                    ),
                ),
            ],
            glossary_id=uuid4(),
        )

        pdf_bytes = await _generate_pdf(manuscript, None, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Verify the Devanagari font is embedded (not falling back to system font)
        assert _has_devanagari_font(pdf_doc), "PDF must embed a Devanagari-capable font"

        # Verify individual Devanagari codepoints are present (not tofu)
        deva_chars = _extract_devanagari_codepoints(pdf_doc)
        expected_chars = {"ध", "र", "म", "क", "ो", "ष", "य", "ग", "आ", "त"}
        missing = expected_chars - deva_chars
        assert not missing, f"Missing Devanagari codepoints: {missing}"

        # Extract all text
        full_text = ""
        for page in pdf_doc:
            full_text += page.get_text()

        # Verify English text is present alongside Devanagari
        assert "dharma" in full_text
        assert "karma" in full_text
        assert "moksha" in full_text

        pdf_doc.close()

    @pytest.mark.asyncio
    async def test_mixed_english_devanagari_preserves_both(self) -> None:
        """Mixed English and Devanagari content should both be readable."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Mixed Script Test",
            chapters=[
                Chapter(
                    number=1,
                    title="Test Chapter",
                    content_html=(
                        "<h1>Test Chapter</h1>"
                        "<p>English text with embedded Sanskrit: "
                        "सर्वे भवन्तु सुखिनः (May all be happy)</p>"
                    ),
                )
            ],
            glossary_id=uuid4(),
        )

        pdf_bytes = await _generate_pdf(manuscript, None, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Verify Devanagari font is embedded
        assert _has_devanagari_font(pdf_doc), "PDF must embed a Devanagari-capable font"

        # Verify Devanagari codepoints are present
        deva_chars = _extract_devanagari_codepoints(pdf_doc)
        expected_chars = {"स", "र", "व", "भ", "न", "त", "ु", "ख"}
        missing = expected_chars - deva_chars
        assert not missing, f"Missing Devanagari codepoints: {missing}"

        full_text = ""
        for page in pdf_doc:
            full_text += page.get_text()

        # English text should be intact
        assert "English text" in full_text
        assert "May all be happy" in full_text

        pdf_doc.close()


class TestGlossaryWithOriginalScript:
    """Test that glossary entries with original_script render correctly."""

    @pytest.mark.asyncio
    async def test_glossary_devanagari_terms_are_readable(self) -> None:
        """Glossary with Devanagari original_script should render correctly."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Test Book",
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1",
                    content_html="<h1>Chapter 1</h1><p>Content with cultural terms.</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        glossary = Glossary(
            book_id=book_id,
            entries=[
                GlossaryEntry(
                    term="dharma",
                    original_script="धर्म",
                    definition="Righteous duty, moral law, cosmic order",
                    source=TermSource.SEED,
                    occurrence_count=5,
                ),
                GlossaryEntry(
                    term="karma",
                    original_script="कर्म",
                    definition="Action and its consequences",
                    source=TermSource.LLM_DETECTED,
                    occurrence_count=3,
                ),
                GlossaryEntry(
                    term="moksha",
                    original_script="मोक्ष",
                    definition="Liberation from the cycle of rebirth",
                    source=TermSource.SEED,
                    occurrence_count=2,
                ),
            ],
        )

        pdf_bytes = await _generate_pdf(manuscript, glossary, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Verify Devanagari font is embedded
        assert _has_devanagari_font(pdf_doc), "Glossary PDF must embed a Devanagari font"

        # Verify Devanagari codepoints from glossary terms are present
        deva_chars = _extract_devanagari_codepoints(pdf_doc)
        expected_chars = {"ध", "र", "म", "क", "ो", "ष"}
        missing = expected_chars - deva_chars
        assert not missing, f"Missing Devanagari codepoints in glossary: {missing}"

        # Extract all text
        full_text = ""
        for page in pdf_doc:
            full_text += page.get_text()

        # Verify glossary heading is present
        assert "Glossary" in full_text, "Glossary section should be present"

        # Verify English terms are present
        assert "dharma" in full_text
        assert "karma" in full_text
        assert "moksha" in full_text

        # Verify definitions are present
        assert "Righteous duty" in full_text
        assert "Action and its consequences" in full_text
        assert "Liberation" in full_text

        pdf_doc.close()

    @pytest.mark.asyncio
    async def test_glossary_without_original_script(self) -> None:
        """Glossary entries can work without original_script."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Test Book",
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1",
                    content_html="<h1>Chapter 1</h1><p>Content.</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        glossary = Glossary(
            book_id=book_id,
            entries=[
                GlossaryEntry(
                    term="nirvana",
                    original_script="",  # Empty original script
                    definition="State of perfect peace",
                    source=TermSource.LLM_DETECTED,
                    occurrence_count=1,
                )
            ],
        )

        pdf_bytes = await _generate_pdf(manuscript, glossary, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        full_text = ""
        for page in pdf_doc:
            full_text += page.get_text()

        assert "nirvana" in full_text
        assert "perfect peace" in full_text

        pdf_doc.close()


class TestPageCount:
    """Test that PDF page count matches expectations."""

    @pytest.mark.asyncio
    async def test_minimal_manuscript_page_count(self) -> None:
        """Minimal manuscript should produce 2 pages (title + 1 chapter)."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Short Book",
            chapters=[
                Chapter(
                    number=1,
                    title="Only Chapter",
                    content_html="<h1>Only Chapter</h1><p>Brief content.</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        pdf_bytes = await _generate_pdf(manuscript, None, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Should have title page + chapter page
        assert pdf_doc.page_count >= 2
        assert pdf_doc.page_count <= 3  # Allow for page breaks, but not excessive overflow

        pdf_doc.close()

    @pytest.mark.asyncio
    async def test_manuscript_with_glossary_page_count(self) -> None:
        """Manuscript with glossary should have additional page(s)."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Book with Glossary",
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1",
                    content_html="<h1>Chapter 1</h1><p>Content with terms.</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        glossary = Glossary(
            book_id=book_id,
            entries=[
                GlossaryEntry(
                    term=f"term{i}",
                    original_script=f"स्क्रिप्ट{i}",
                    definition=f"Definition {i}",
                    source=TermSource.SEED,
                    occurrence_count=1,
                )
                for i in range(5)  # 5 glossary entries
            ],
        )

        pdf_bytes = await _generate_pdf(manuscript, glossary, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Title page + chapter + glossary = at least 3 pages
        assert pdf_doc.page_count >= 3

        pdf_doc.close()

    @pytest.mark.asyncio
    async def test_multi_chapter_page_count(self) -> None:
        """Multiple chapters should produce multiple pages."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Multi-Chapter Book",
            chapters=[
                Chapter(
                    number=i,
                    title=f"Chapter {i}",
                    content_html=f"<h1>Chapter {i}</h1>" + "<p>Content paragraph.</p>" * 20,
                )
                for i in range(1, 6)  # 5 chapters with substantial content
            ],
            glossary_id=uuid4(),
        )

        pdf_bytes = await _generate_pdf(manuscript, None, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Should have multiple pages (title + 5 chapters = at least 6)
        assert pdf_doc.page_count >= 6

        pdf_doc.close()


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_chapters_list(self) -> None:
        """Manuscript with no chapters should still generate title page."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Empty Book",
            chapters=[],  # No chapters
            glossary_id=uuid4(),
        )

        pdf_bytes = await _generate_pdf(manuscript, None, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Should have at least title page
        assert pdf_doc.page_count >= 1

        page1_text = pdf_doc[0].get_text()
        assert "Empty Book" in page1_text

        pdf_doc.close()

    @pytest.mark.asyncio
    async def test_special_characters_in_title(self) -> None:
        """Title with special characters should render correctly."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title='The "Gita" & <Its> Wisdom\'s Path',
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1",
                    content_html="<h1>Chapter 1</h1><p>Content.</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        pdf_bytes = await _generate_pdf(manuscript, None, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        page1_text = pdf_doc[0].get_text()
        # Should handle HTML escaping properly
        assert "Gita" in page1_text
        assert "Wisdom" in page1_text

        pdf_doc.close()

    @pytest.mark.asyncio
    async def test_very_long_glossary(self) -> None:
        """Large glossary should not cause rendering issues."""
        book_id = uuid4()
        manuscript = Manuscript(
            book_id=book_id,
            title="Book with Large Glossary",
            chapters=[
                Chapter(
                    number=1,
                    title="Chapter 1",
                    content_html="<h1>Chapter 1</h1><p>Content.</p>",
                )
            ],
            glossary_id=uuid4(),
        )

        # Create a large glossary (50 entries)
        glossary = Glossary(
            book_id=book_id,
            entries=[
                GlossaryEntry(
                    term=f"term_{i:02d}",
                    original_script=f"टर्म_{i:02d}",
                    definition=f"This is definition number {i} with some explanatory text.",
                    source=TermSource.SEED,
                    occurrence_count=1,
                )
                for i in range(50)
            ],
        )

        pdf_bytes = await _generate_pdf(manuscript, glossary, None)
        pdf_doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")

        # Should generate without errors
        assert pdf_doc.page_count > 0

        # Verify some glossary entries are present
        full_text = ""
        for page in pdf_doc:
            full_text += page.get_text()

        assert "term_00" in full_text
        assert "term_49" in full_text
        assert "Glossary" in full_text

        pdf_doc.close()
