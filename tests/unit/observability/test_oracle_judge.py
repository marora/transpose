"""Unit tests for Oracle Layer C translation quality judge."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from transpose.models.enums import SectionType
from transpose.models.translation import Chunk, Translation
from transpose.observability.oracle_judge import (
    OracleScore,
    judge_translation_quality,
    select_stratified_sample,
)


class TestSelectStratifiedSample:
    """Tests for stratified chunk sampling."""

    def test_empty_chunks_returns_empty(self):
        """Empty chunk list should return empty sample."""
        assert select_stratified_sample([]) == []

    def test_single_chunk_returns_one(self):
        """Single chunk should return that chunk."""
        chunk = Chunk(
            id=uuid4(),
            book_id=uuid4(),
            sequence=0,
            source_text="test",
            token_count=10,
            page_start=1,
            page_end=1,
            section_type=SectionType.PROSE,
            chapter_ref=None,
        )
        result = select_stratified_sample([chunk])
        assert len(result) == 1
        assert result[0] == chunk

    def test_stratified_distribution(self):
        """Should sample from early/mid/late bins."""
        # Create 30 chunks
        chunks = [
            Chunk(
                id=uuid4(),
                book_id=uuid4(),
                sequence=i,
                source_text=f"chunk {i}",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
            for i in range(30)
        ]

        # 5% of 30 = 1.5, rounds to 1, but we want at least 1
        sample = select_stratified_sample(chunks, sample_fraction=0.05)

        # Should get at least 1 chunk
        assert len(sample) >= 1

        # With 10% we should get 3 chunks (30 * 0.1 = 3)
        sample = select_stratified_sample(chunks, sample_fraction=0.10)
        assert len(sample) == 3

        # Results should be sorted by sequence
        for i in range(len(sample) - 1):
            assert sample[i].sequence < sample[i + 1].sequence

    def test_large_sample_respects_fraction(self):
        """Large chunk list should respect sample fraction."""
        chunks = [
            Chunk(
                id=uuid4(),
                book_id=uuid4(),
                sequence=i,
                source_text=f"chunk {i}",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
            for i in range(300)
        ]

        # 5% of 300 = 15
        sample = select_stratified_sample(chunks, sample_fraction=0.05)
        assert len(sample) == 15

        # Results should be sorted by sequence
        for i in range(len(sample) - 1):
            assert sample[i].sequence < sample[i + 1].sequence

    def test_minimum_one_chunk(self):
        """Should return at least 1 chunk even for tiny sample fractions."""
        chunks = [
            Chunk(
                id=uuid4(),
                book_id=uuid4(),
                sequence=0,
                source_text="chunk 0",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
        ]

        # Even with 0.001% sample, should get at least 1
        sample = select_stratified_sample(chunks, sample_fraction=0.00001)
        assert len(sample) == 1


@pytest.mark.asyncio
class TestJudgeTranslationQuality:
    """Tests for the Anthropic judge integration."""

    async def test_no_api_key_returns_none(self):
        """Should return None when API key is not configured."""
        book_id = uuid4()
        chunks = [
            Chunk(
                id=uuid4(),
                book_id=book_id,
                sequence=0,
                source_text="test",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
        ]
        translations = []

        result = await judge_translation_quality(
            book_id=book_id,
            chunks=chunks,
            translations=translations,
            anthropic_api_key="",
        )

        assert result is None

    async def test_empty_chunks_returns_none(self):
        """Should return None when chunks list is empty."""
        book_id = uuid4()

        result = await judge_translation_quality(
            book_id=book_id,
            chunks=[],
            translations=[],
            anthropic_api_key="test-key",
        )

        assert result is None

    async def test_empty_translations_returns_none(self):
        """Should return None when translations list is empty."""
        book_id = uuid4()
        chunks = [
            Chunk(
                id=uuid4(),
                book_id=book_id,
                sequence=0,
                source_text="test",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
        ]

        result = await judge_translation_quality(
            book_id=book_id,
            chunks=chunks,
            translations=[],
            anthropic_api_key="test-key",
        )

        assert result is None

    async def test_anthropic_api_error_returns_none(self, monkeypatch):
        """Should return None when Anthropic API call fails."""
        book_id = uuid4()
        chunk_id = uuid4()
        chunks = [
            Chunk(
                id=chunk_id,
                book_id=book_id,
                sequence=0,
                source_text="test source",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
        ]
        translations = [
            Translation(
                id=uuid4(),
                chunk_id=chunk_id,
                book_id=book_id,
                translated_text="test translation",
                model_version="gpt-4o",
                cultural_terms=[],
                prompt_tokens=10,
                completion_tokens=10,
                raw_response={},
            )
        ]

        # Mock the Anthropic API to raise an error
        async def mock_call_anthropic(*args, **kwargs):
            raise Exception("API error")

        from transpose.observability import oracle_judge

        monkeypatch.setattr(oracle_judge, "_call_anthropic_judge", mock_call_anthropic)

        result = await judge_translation_quality(
            book_id=book_id,
            chunks=chunks,
            translations=translations,
            anthropic_api_key="test-key",
        )

        assert result is None

    async def test_successful_judge_call(self, monkeypatch):
        """Should return OracleScore when judge call succeeds."""
        book_id = uuid4()
        chunk_id = uuid4()
        chunks = [
            Chunk(
                id=chunk_id,
                book_id=book_id,
                sequence=0,
                source_text="test source",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
        ]
        translations = [
            Translation(
                id=uuid4(),
                chunk_id=chunk_id,
                book_id=book_id,
                translated_text="test translation",
                model_version="gpt-4o",
                cultural_terms=[],
                prompt_tokens=10,
                completion_tokens=10,
                raw_response={},
            )
        ]

        # Mock the Anthropic API to return a valid response
        mock_response = """{
            "composite_score": 85,
            "fluency": 90,
            "cultural_register": 80,
            "terminology_nuance": 85
        }"""

        async def mock_call_anthropic(*args, **kwargs):
            return mock_response

        from transpose.observability import oracle_judge

        monkeypatch.setattr(oracle_judge, "_call_anthropic_judge", mock_call_anthropic)

        result = await judge_translation_quality(
            book_id=book_id,
            chunks=chunks,
            translations=translations,
            anthropic_api_key="test-key",
        )

        assert result is not None
        assert isinstance(result, OracleScore)
        assert result.composite_score == 85
        assert result.fluency == 90
        assert result.cultural_register == 80
        assert result.terminology_nuance == 85
        assert len(result.sampled_chunk_ids) == 1
        assert result.sampled_chunk_ids[0] == str(chunk_id)

    async def test_invalid_json_response_returns_none(self, monkeypatch):
        """Should return None when judge returns invalid JSON."""
        book_id = uuid4()
        chunk_id = uuid4()
        chunks = [
            Chunk(
                id=chunk_id,
                book_id=book_id,
                sequence=0,
                source_text="test source",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
        ]
        translations = [
            Translation(
                id=uuid4(),
                chunk_id=chunk_id,
                book_id=book_id,
                translated_text="test translation",
                model_version="gpt-4o",
                cultural_terms=[],
                prompt_tokens=10,
                completion_tokens=10,
                raw_response={},
            )
        ]

        # Mock the Anthropic API to return invalid JSON
        async def mock_call_anthropic(*args, **kwargs):
            return "not valid json"

        from transpose.observability import oracle_judge

        monkeypatch.setattr(oracle_judge, "_call_anthropic_judge", mock_call_anthropic)

        result = await judge_translation_quality(
            book_id=book_id,
            chunks=chunks,
            translations=translations,
            anthropic_api_key="test-key",
        )

        assert result is None

    async def test_missing_score_fields_returns_none(self, monkeypatch):
        """Should return None when judge response is missing required fields."""
        book_id = uuid4()
        chunk_id = uuid4()
        chunks = [
            Chunk(
                id=chunk_id,
                book_id=book_id,
                sequence=0,
                source_text="test source",
                token_count=10,
                page_start=1,
                page_end=1,
                section_type=SectionType.PROSE,
                chapter_ref=None,
            )
        ]
        translations = [
            Translation(
                id=uuid4(),
                chunk_id=chunk_id,
                book_id=book_id,
                translated_text="test translation",
                model_version="gpt-4o",
                cultural_terms=[],
                prompt_tokens=10,
                completion_tokens=10,
                raw_response={},
            )
        ]

        # Mock the Anthropic API to return incomplete response
        mock_response = '{"composite_score": 85}'  # Missing other fields

        async def mock_call_anthropic(*args, **kwargs):
            return mock_response

        from transpose.observability import oracle_judge

        monkeypatch.setattr(oracle_judge, "_call_anthropic_judge", mock_call_anthropic)

        result = await judge_translation_quality(
            book_id=book_id,
            chunks=chunks,
            translations=translations,
            anthropic_api_key="test-key",
        )

        assert result is None
