"""Tests for data models."""

from uuid import UUID

from transpose.models.book import Book
from transpose.models.enums import BookStatus, SourceLanguage
from transpose.models.glossary import GlossaryEntry
from transpose.models.translation import Chunk


class TestBookModel:
    def test_book_defaults(self) -> None:
        book = Book(
            title="Test",
            source_language=SourceLanguage.HINDI,
            source_hash="abc123",
            source_blob_uri="https://example.com/test.pdf",
        )
        assert book.status == BookStatus.INGESTED
        assert book.page_count == 0
        assert isinstance(book.id, UUID)

    def test_book_with_author(self) -> None:
        book = Book(
            title="Test",
            author="Author",
            source_language=SourceLanguage.PUNJABI,
            source_hash="def456",
            source_blob_uri="https://example.com/test.pdf",
        )
        assert book.author == "Author"
        assert book.source_language == SourceLanguage.PUNJABI


class TestChunkModel:
    def test_chunk_defaults(self) -> None:
        from transpose.models.enums import SectionType

        chunk = Chunk(
            book_id=UUID("12345678-1234-1234-1234-123456789012"),
            sequence=0,
            source_text="test text",
            token_count=5,
            page_start=1,
            page_end=1,
        )
        assert chunk.section_type == SectionType.PROSE
        assert chunk.chapter_ref is None


class TestGlossaryEntry:
    def test_entry_creation(self) -> None:
        from transpose.models.enums import TermSource

        entry = GlossaryEntry(
            term="dharma",
            original_script="धर्म",
            definition="Righteous duty",
            source=TermSource.SEED,
            occurrence_count=5,
        )
        assert entry.needs_review is False
