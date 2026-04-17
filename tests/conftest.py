"""Shared test fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from transpose.config.seed_glossary import SEED_TERMS
from transpose.models.book import Book
from transpose.models.enums import BookStatus, SectionType, SourceLanguage, TermSource
from transpose.models.glossary import GlossaryEntry
from transpose.models.translation import Chunk

if TYPE_CHECKING:
    pass


@pytest.fixture
def sample_book_data() -> dict:
    """Minimal book data for testing."""
    return {
        "title": "Test Book",
        "author": "Test Author",
        "source_language": "hindi",
    }


@pytest.fixture
def sample_book_id() -> UUID:
    """Fixed UUID for testing."""
    return UUID("12345678-1234-1234-1234-123456789012")


@pytest.fixture
def sample_book(sample_book_id: UUID) -> Book:
    """Sample Book instance for testing."""
    return Book(
        id=sample_book_id,
        title="Bhagavad Gita",
        author="Vyasa",
        source_language=SourceLanguage.HINDI,
        source_hash="abc123def456",
        source_blob_uri="https://storage.blob.core.windows.net/books/gita.pdf",
        page_count=18,
        status=BookStatus.INGESTED,
    )


@pytest.fixture
def sample_chunk(sample_book_id: UUID) -> Chunk:
    """Sample Chunk instance for testing."""
    return Chunk(
        id=uuid4(),
        book_id=sample_book_id,
        sequence=0,
        source_text="योगस्थः कुरु कर्माणि सङ्गं त्यक्त्वा धनञ्जय। सिद्ध्यसिद्ध्योः समो भूत्वा समत्वं योग उच्यते॥",
        token_count=25,
        page_start=1,
        page_end=1,
        section_type=SectionType.VERSE,
        chapter_ref="Chapter 2",
    )


@pytest.fixture
def sample_glossary_entry() -> GlossaryEntry:
    """Sample GlossaryEntry for testing."""
    return GlossaryEntry(
        term="dharma",
        original_script="धर्म",
        definition="Righteous duty, moral law, cosmic order",
        source=TermSource.SEED,
        occurrence_count=5,
        first_chapter="Chapter 1",
        needs_review=False,
    )


@pytest.fixture
def seed_glossary_dict() -> dict[str, tuple[str, str]]:
    """Seed glossary as a dictionary."""
    return {term: (script, defn) for term, script, defn in SEED_TERMS}


@pytest.fixture
def mock_database() -> AsyncMock:
    """Mock Database service."""
    db = AsyncMock(spec=["execute", "fetch_one", "fetch_all", "close"])
    db.execute = AsyncMock()
    db.fetch_one = AsyncMock(return_value=None)
    db.fetch_all = AsyncMock(return_value=[])
    return db


@pytest.fixture
def mock_state() -> AsyncMock:
    """Mock PipelineState service."""
    state = AsyncMock()
    state.set_pipeline_status = AsyncMock()
    state.get_pipeline_status = AsyncMock()
    state.set_progress = AsyncMock()
    state.acquire_lock = AsyncMock(return_value=True)
    state.release_lock = AsyncMock()
    return state


@pytest.fixture
def mock_blob_client() -> AsyncMock:
    """Mock BlobClient service."""
    blob = AsyncMock(spec=["upload_file", "download_file", "get_blob_url"])
    blob.upload_file = AsyncMock(
        return_value="https://storage.blob.core.windows.net/books/test.pdf"
    )
    blob.download_file = AsyncMock(return_value=b"fake pdf content")
    blob.get_blob_url = AsyncMock(
        return_value="https://storage.blob.core.windows.net/books/test.pdf"
    )
    return blob


@pytest.fixture
def mock_ocr_client() -> AsyncMock:
    """Mock OcrClient service."""
    ocr = AsyncMock(spec=["extract_text_from_pdf", "extract_text_with_azure_di"])
    ocr.extract_text_from_pdf = AsyncMock(
        return_value=[
            {"page_number": 1, "text": "Sample text from page 1", "confidence": 0.95},
            {"page_number": 2, "text": "Sample text from page 2", "confidence": 0.98},
        ]
    )
    ocr.extract_text_with_azure_di = AsyncMock(
        return_value=[
            {
                "page_number": 1,
                "text": "Sample scanned text",
                "confidence": 0.85,
                "metadata": {"bounding_boxes": [], "reading_order": []},
            }
        ]
    )
    return ocr


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    """Mock LlmClient service."""
    llm = AsyncMock(spec=["translate_chunk", "detect_cultural_terms"])
    
    # Mock translation response with cultural terms
    llm.translate_chunk = AsyncMock(
        return_value={
            "translated_text": (
                "Established in yoga, perform actions abandoning attachment, "
                "O Dhananjaya. Being equal in success and failure, "
                "such equanimity is called yoga."
            ),
            "cultural_terms": [
                {
                    "term": "yoga",
                    "original_script": "योग",
                    "definition": "Spiritual discipline; union with the divine",
                }
            ],
            "prompt_tokens": 150,
            "completion_tokens": 80,
            "model_version": "gpt-4",
        }
    )
    
    llm.detect_cultural_terms = AsyncMock(
        return_value=[
            {
                "term": "dharma",
                "original_script": "धर्म",
                "definition": "Righteous duty",
            }
        ]
    )
    
    return llm


@pytest.fixture
def mock_service_context(
    mock_database: AsyncMock,
    mock_state: AsyncMock,
    mock_blob_client: AsyncMock,
    mock_ocr_client: AsyncMock,
    mock_llm_client: AsyncMock,
) -> MagicMock:
    """Complete mock ServiceContext with all dependencies."""
    context = MagicMock()
    context.db = mock_database
    context.state = mock_state
    context.blob = mock_blob_client
    context.ocr = mock_ocr_client
    context.llm = mock_llm_client
    return context
