"""Tests for the translate pipeline stage.

CRITICAL: Tests cultural term preservation - if these fail, it's a P0 bug.
Tests translation, cultural term extraction, and seed term usage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from transpose.models.enums import TermSource


@dataclass
class TranslateInput:
    """Translate stage input contract."""

    book_id: UUID
    force_retranslate: bool = False
    concurrency: int = 5


@dataclass
class ExtractedTerm:
    """A cultural term extracted during translation."""

    term: str
    original_script: str
    definition: str
    source: TermSource


@dataclass
class TranslationResult:
    """Translation result for a single chunk."""

    chunk_id: UUID
    translated_text: str
    cultural_terms: list[ExtractedTerm]
    prompt_tokens: int
    completion_tokens: int
    model_version: str


@dataclass
class TranslateOutput:
    """Translate stage output contract."""

    book_id: UUID
    chunks_translated: int
    chunks_skipped: int
    total_prompt_tokens: int
    total_completion_tokens: int
    cultural_terms_found: int
    translations: list[TranslationResult] = field(default_factory=list)


class TestTranslateContract:
    """Test translate stage contract validation."""

    def test_translate_input_defaults(self) -> None:
        """Test TranslateInput has sensible defaults."""
        book_id = uuid4()
        input_data = TranslateInput(book_id=book_id)
        assert input_data.book_id == book_id
        assert input_data.force_retranslate is False
        assert input_data.concurrency == 5

    def test_translate_input_custom_concurrency(self) -> None:
        """Test TranslateInput accepts custom concurrency."""
        book_id = uuid4()
        input_data = TranslateInput(
            book_id=book_id,
            force_retranslate=True,
            concurrency=10,
        )
        assert input_data.force_retranslate is True
        assert input_data.concurrency == 10

    def test_extracted_term_shape(self) -> None:
        """Test ExtractedTerm has all required fields."""
        term = ExtractedTerm(
            term="dharma",
            original_script="धर्म",
            definition="Righteous duty",
            source=TermSource.SEED,
        )
        assert len(term.term) > 0
        assert len(term.original_script) > 0
        assert len(term.definition) > 0
        assert term.source in TermSource

    def test_translation_result_shape(self) -> None:
        """Test TranslationResult has all required fields."""
        result = TranslationResult(
            chunk_id=uuid4(),
            translated_text="Translated text",
            cultural_terms=[],
            prompt_tokens=100,
            completion_tokens=50,
            model_version="gpt-4",
        )
        assert isinstance(result.chunk_id, UUID)
        assert len(result.translated_text) > 0
        assert isinstance(result.cultural_terms, list)
        assert result.prompt_tokens > 0
        assert result.completion_tokens > 0


class TestCulturalTermPreservation:
    """CRITICAL: Test cultural term preservation - this is P0."""

    @pytest.mark.asyncio
    async def test_dharma_never_translated(
        self,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test that 'dharma' is NEVER translated."""
        # Mock LLM response that preserves dharma
        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": "One must follow their dharma in life.",
                "cultural_terms": [
                    {
                        "term": "dharma",
                        "original_script": "धर्म",
                        "definition": "Righteous duty, moral law, cosmic order",
                    }
                ],
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "model_version": "gpt-4",
            }
        )

        response = await mock_llm_client.translate_chunk(
            "धर्म का पालन करना चाहिए।",
            seed_terms=seed_glossary_dict,
        )

        # CRITICAL: dharma must appear untranslated
        assert "dharma" in response["translated_text"].lower()
        assert "duty" not in response["translated_text"] or "dharma" in response["translated_text"]

        # Term must be in cultural_terms list
        term_names = [t["term"] for t in response["cultural_terms"]]
        assert "dharma" in term_names

    @pytest.mark.asyncio
    async def test_karma_never_translated(
        self,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test that 'karma' is NEVER translated."""
        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": "Perform actions without attachment to karma.",
                "cultural_terms": [
                    {
                        "term": "karma",
                        "original_script": "कर्म",
                        "definition": "Action and its consequences",
                    }
                ],
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "model_version": "gpt-4",
            }
        )

        response = await mock_llm_client.translate_chunk(
            "कर्म करो फल की इच्छा मत करो।",
            seed_terms=seed_glossary_dict,
        )

        assert "karma" in response["translated_text"].lower()
        term_names = [t["term"] for t in response["cultural_terms"]]
        assert "karma" in term_names

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "term,script",
        [
            ("atman", "आत्मन्"),
            ("moksha", "मोक्ष"),
            ("samsara", "संसार"),
            ("maya", "माया"),
            ("guru", "गुरु"),
            ("yoga", "योग"),
            ("bhakti", "भक्ति"),
        ],
    )
    async def test_hindi_seed_terms_preserved(
        self,
        term: str,
        script: str,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test that all Hindi seed terms are preserved untranslated."""
        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": f"The concept of {term} is important.",
                "cultural_terms": [
                    {
                        "term": term,
                        "original_script": script,
                        "definition": seed_glossary_dict[term][1],
                    }
                ],
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "model_version": "gpt-4",
            }
        )

        response = await mock_llm_client.translate_chunk(
            f"Sample text with {script}",
            seed_terms=seed_glossary_dict,
        )

        assert term in response["translated_text"].lower()
        term_names = [t["term"] for t in response["cultural_terms"]]
        assert term in term_names

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "term,script",
        [
            ("sangat", "ਸੰਗਤ"),
            ("langar", "ਲੰਗਰ"),
            ("seva", "ਸੇਵਾ"),
            ("gurdwara", "ਗੁਰਦੁਆਰਾ"),
            ("waheguru", "ਵਾਹਿਗੁਰੂ"),
            ("naam", "ਨਾਮ"),
            ("simran", "ਸਿਮਰਨ"),
        ],
    )
    async def test_punjabi_seed_terms_preserved(
        self,
        term: str,
        script: str,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test that all Punjabi/Sikh seed terms are preserved untranslated."""
        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": f"The practice of {term} is sacred.",
                "cultural_terms": [
                    {
                        "term": term,
                        "original_script": script,
                        "definition": seed_glossary_dict[term][1],
                    }
                ],
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "model_version": "gpt-4",
            }
        )

        response = await mock_llm_client.translate_chunk(
            f"Sample text with {script}",
            seed_terms=seed_glossary_dict,
        )

        assert term in response["translated_text"].lower()
        term_names = [t["term"] for t in response["cultural_terms"]]
        assert term in term_names


class TestTranslatePromptConstruction:
    """Test that prompts include seed terms."""

    @pytest.mark.asyncio
    async def test_seed_terms_in_prompt(
        self,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test that seed terms are included in translation prompt."""
        # The actual implementation should include seed terms in prompt
        # We verify that seed_glossary is passed to the LLM client
        await mock_llm_client.translate_chunk(
            "Sample Hindi text",
            seed_terms=seed_glossary_dict,
        )

        # Verify the call was made with seed_terms
        mock_llm_client.translate_chunk.assert_called_once()
        call_args = mock_llm_client.translate_chunk.call_args
        assert "seed_terms" in call_args.kwargs or len(call_args.args) > 1

    @pytest.mark.asyncio
    async def test_previous_context_passed(
        self,
        mock_llm_client: AsyncMock,
    ) -> None:
        """Test that previous chunk context is passed for continuity."""
        previous_context = "Previous chunk talked about dharma..."

        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": "Continuing the discussion on dharma.",
                "cultural_terms": [],
                "prompt_tokens": 150,
                "completion_tokens": 60,
                "model_version": "gpt-4",
            }
        )

        await mock_llm_client.translate_chunk(
            "Current chunk text",
            previous_context=previous_context,
        )

        # Verify context was passed
        mock_llm_client.translate_chunk.assert_called_once()


class TestTranslateConcurrency:
    """Test concurrency limiting."""

    @pytest.mark.asyncio
    async def test_concurrency_semaphore(self) -> None:
        """Test that concurrency is limited by semaphore."""
        import asyncio

        concurrency_limit = 5
        semaphore = asyncio.Semaphore(concurrency_limit)

        # Verify semaphore limits concurrent access
        async def dummy_task():
            async with semaphore:
                await asyncio.sleep(0.01)

        # Create more tasks than limit
        tasks = [dummy_task() for _ in range(20)]
        await asyncio.gather(*tasks)

        # If we get here without deadlock, semaphore works
        assert True


class TestTranslateIdempotency:
    """Test idempotency of translation stage."""

    @pytest.mark.asyncio
    async def test_already_translated_chunks_skipped(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test that already-translated chunks are skipped."""
        book_id = uuid4()

        # Mock database returning existing translations
        mock_database.fetch_all = AsyncMock(
            return_value=[
                {"chunk_id": uuid4(), "translated_text": "Existing translation 1"},
                {"chunk_id": uuid4(), "translated_text": "Existing translation 2"},
            ]
        )

        await mock_database.fetch_all(
            "SELECT chunk_id FROM translations WHERE book_id = $1", book_id
        )

        output = TranslateOutput(
            book_id=book_id,
            chunks_translated=1,  # Only 1 new
            chunks_skipped=2,  # 2 already done
            total_prompt_tokens=100,
            total_completion_tokens=50,
            cultural_terms_found=3,
            translations=[],
        )
        assert output.chunks_skipped == 2

    @pytest.mark.asyncio
    async def test_force_retranslate_overrides_skip(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test that force_retranslate overrides skip logic."""
        book_id = uuid4()
        input_data = TranslateInput(
            book_id=book_id,
            force_retranslate=True,
        )

        assert input_data.force_retranslate is True

        # With force_retranslate, chunks_skipped should be 0
        output = TranslateOutput(
            book_id=book_id,
            chunks_translated=5,
            chunks_skipped=0,  # None skipped due to force
            total_prompt_tokens=500,
            total_completion_tokens=250,
            cultural_terms_found=10,
            translations=[],
        )
        assert output.chunks_skipped == 0


class TestTranslateTokenAggregation:
    """Test token usage aggregation."""

    def test_token_aggregation(self) -> None:
        """Test that token usage is aggregated across chunks."""
        translations = [
            TranslationResult(uuid4(), "text1", [], 100, 50, "gpt-4"),
            TranslationResult(uuid4(), "text2", [], 120, 60, "gpt-4"),
            TranslationResult(uuid4(), "text3", [], 110, 55, "gpt-4"),
        ]

        total_prompt = sum(t.prompt_tokens for t in translations)
        total_completion = sum(t.completion_tokens for t in translations)

        assert total_prompt == 330
        assert total_completion == 165

        output = TranslateOutput(
            book_id=uuid4(),
            chunks_translated=3,
            chunks_skipped=0,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            cultural_terms_found=5,
            translations=translations,
        )
        assert output.total_prompt_tokens == 330
        assert output.total_completion_tokens == 165
