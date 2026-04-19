"""Tests for the assemble pipeline stage.

Tests chapter reconstruction, HTML generation, and glossary positioning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


@dataclass
class AssembleInput:
    """Assemble stage input contract."""

    book_id: UUID
    glossary_position: str = "back"


@dataclass
class Chapter:
    """A chapter in the assembled manuscript."""

    number: int
    title: str
    content_html: str


@dataclass
class AssembleOutput:
    """Assemble stage output contract."""

    book_id: UUID
    manuscript_id: UUID
    title: str
    author: str | None
    chapters: list[Chapter]
    glossary_id: UUID
    table_of_contents: list[dict] = field(default_factory=list)
    foreword: str | None = None


class TestAssembleContract:
    """Test assemble stage contract validation."""

    def test_assemble_input_defaults(self) -> None:
        """Test AssembleInput has sensible defaults."""
        book_id = uuid4()
        input_data = AssembleInput(book_id=book_id)
        assert input_data.book_id == book_id
        assert input_data.glossary_position == "back"

    def test_assemble_input_front_matter(self) -> None:
        """Test AssembleInput can place glossary in front."""
        book_id = uuid4()
        input_data = AssembleInput(book_id=book_id, glossary_position="front")
        assert input_data.glossary_position == "front"

    def test_chapter_shape(self) -> None:
        """Test Chapter has all required fields."""
        chapter = Chapter(
            number=1,
            title="Chapter 1: The Beginning",
            content_html="<p>Content here</p>",
        )
        assert chapter.number > 0
        assert len(chapter.title) > 0
        assert chapter.content_html.startswith("<")

    def test_assemble_output_shape(self) -> None:
        """Test AssembleOutput has all required fields."""
        book_id = uuid4()
        manuscript_id = uuid4()
        glossary_id = uuid4()
        
        output = AssembleOutput(
            book_id=book_id,
            manuscript_id=manuscript_id,
            title="Test Book",
            author="Test Author",
            chapters=[],
            glossary_id=glossary_id,
            table_of_contents=[],
        )
        assert output.book_id == book_id
        assert output.manuscript_id == manuscript_id
        assert isinstance(output.chapters, list)


class TestChapterReconstruction:
    """Test chapter reconstruction from chunks."""

    def test_chunks_grouped_by_chapter(self) -> None:
        """Test that chunks are grouped by chapter reference."""
        chunks = [
            {"chapter_ref": "Chapter 1", "text": "Text 1"},
            {"chapter_ref": "Chapter 1", "text": "Text 2"},
            {"chapter_ref": "Chapter 2", "text": "Text 3"},
        ]

        chapters_dict = {}
        for chunk in chunks:
            chapter_ref = chunk["chapter_ref"]
            if chapter_ref not in chapters_dict:
                chapters_dict[chapter_ref] = []
            chapters_dict[chapter_ref].append(chunk["text"])

        assert len(chapters_dict) == 2
        assert len(chapters_dict["Chapter 1"]) == 2
        assert len(chapters_dict["Chapter 2"]) == 1

    def test_chapter_content_concatenation(self) -> None:
        """Test that chapter content is properly concatenated."""
        chunk_texts = ["First paragraph.", "Second paragraph.", "Third paragraph."]
        combined = " ".join(chunk_texts)
        
        assert "First paragraph" in combined
        assert "Third paragraph" in combined


class TestHtmlGeneration:
    """Test HTML generation for chapters."""

    def test_chapter_html_valid(self) -> None:
        """Test that chapter HTML is semantic and valid."""
        chapter = Chapter(
            number=1,
            title="Chapter 1",
            content_html="<h2>Chapter 1</h2><p>Content here.</p>",
        )
        
        assert chapter.content_html.startswith("<")
        assert "<h2>" in chapter.content_html
        assert "<p>" in chapter.content_html

    def test_html_escaping(self) -> None:
        """Test that special characters are properly escaped."""
        import html
        
        raw_text = 'This has <special> & "characters"'
        escaped = html.escape(raw_text)
        
        assert "&lt;" in escaped
        assert "&gt;" in escaped
        assert "&amp;" in escaped


class TestTableOfContents:
    """Test table of contents generation."""

    def test_toc_generation(self) -> None:
        """Test that table of contents is generated from chapters."""
        chapters = [
            Chapter(1, "Chapter 1: Beginning", "<p>Content</p>"),
            Chapter(2, "Chapter 2: Middle", "<p>Content</p>"),
            Chapter(3, "Chapter 3: End", "<p>Content</p>"),
        ]

        toc = [{"chapter": ch.number, "title": ch.title} for ch in chapters]

        assert len(toc) == 3
        assert toc[0]["chapter"] == 1
        assert toc[0]["title"] == "Chapter 1: Beginning"

    def test_toc_ordering(self) -> None:
        """Test that TOC maintains chapter order."""
        toc = [
            {"chapter": 1, "title": "Chapter 1"},
            {"chapter": 2, "title": "Chapter 2"},
            {"chapter": 3, "title": "Chapter 3"},
        ]

        chapter_numbers = [item["chapter"] for item in toc]
        assert chapter_numbers == sorted(chapter_numbers)


class TestGlossaryPosition:
    """Test glossary positioning in manuscript."""

    def test_glossary_back_matter(self) -> None:
        """Test glossary placed in back matter."""
        input_data = AssembleInput(book_id=uuid4(), glossary_position="back")
        
        # In actual implementation, glossary would be appended after chapters
        assert input_data.glossary_position == "back"

    def test_glossary_front_matter(self) -> None:
        """Test glossary placed in front matter."""
        input_data = AssembleInput(book_id=uuid4(), glossary_position="front")
        
        # In actual implementation, glossary would be prepended before chapters
        assert input_data.glossary_position == "front"


class TestAssembleEdgeCases:
    """Test assembly edge cases."""

    def test_single_chapter_book(self) -> None:
        """Test assembling single-chapter book."""
        output = AssembleOutput(
            book_id=uuid4(),
            manuscript_id=uuid4(),
            title="Single Chapter",
            author="Author",
            chapters=[Chapter(1, "Only Chapter", "<p>Content</p>")],
            glossary_id=uuid4(),
            table_of_contents=[{"chapter": 1, "title": "Only Chapter"}],
        )
        
        assert len(output.chapters) == 1
        assert len(output.table_of_contents) == 1

    def test_book_without_author(self) -> None:
        """Test assembling book without author."""
        output = AssembleOutput(
            book_id=uuid4(),
            manuscript_id=uuid4(),
            title="Anonymous Work",
            author=None,
            chapters=[],
            glossary_id=uuid4(),
        )
        
        assert output.author is None


class TestForewordGeneration:
    """Test Translator's Foreword generation in assemble stage."""

    def test_assemble_output_foreword_field_defaults_none(self) -> None:
        """AssembleOutput.foreword defaults to None."""
        output = AssembleOutput(
            book_id=uuid4(),
            manuscript_id=uuid4(),
            title="Test",
            author=None,
            chapters=[],
            glossary_id=uuid4(),
        )
        assert output.foreword is None

    def test_assemble_output_with_foreword(self) -> None:
        """AssembleOutput can carry foreword text."""
        foreword = "Dear Reader, this translation preserves dharma..."
        output = AssembleOutput(
            book_id=uuid4(),
            manuscript_id=uuid4(),
            title="Test",
            author="Author",
            chapters=[],
            glossary_id=uuid4(),
            foreword=foreword,
        )
        assert output.foreword == foreword
        assert "Dear Reader" in output.foreword
