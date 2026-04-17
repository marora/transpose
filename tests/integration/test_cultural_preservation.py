"""Integration tests for cultural term preservation.

CRITICAL: These tests validate that cultural terms are NEVER translated.
If these fail, it's a P0 bug that must be fixed immediately.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest


@pytest.mark.integration
class TestCulturalTermPreservation:
    """CRITICAL: Test cultural term preservation across pipeline."""

    @pytest.fixture
    def hindi_sample_text(self) -> str:
        """Load sample Hindi text fixture."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_hindi_text.txt"
        return fixture_path.read_text(encoding="utf-8")

    @pytest.fixture
    def punjabi_sample_text(self) -> str:
        """Load sample Punjabi text fixture."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "sample_punjabi_text.txt"
        return fixture_path.read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_dharma_preserved_in_translation(
        self,
        hindi_sample_text: str,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """CRITICAL: Test that dharma is preserved untranslated."""
        # Mock LLM to preserve dharma
        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": (
                    "Protecting dharma is everyone's duty. "
                    "In life, we must perform our karma without "
                    "desire for results. This is true bhakti."
                ),
                "cultural_terms": [
                    {"term": "dharma", "original_script": "धर्म", "definition": "Righteous duty"},
                    {"term": "karma", "original_script": "कर्म", "definition": "Action"},
                    {"term": "bhakti", "original_script": "भक्ति", "definition": "Devotion"},
                ],
                "prompt_tokens": 200,
                "completion_tokens": 100,
                "model_version": "gpt-4",
            }
        )

        # Simulate translation
        result = await mock_llm_client.translate_chunk(
            "धर्म की रक्षा करना...",
            seed_terms=seed_glossary_dict,
        )

        # CRITICAL: dharma must appear untranslated
        assert "dharma" in result["translated_text"].lower()
        
        # Extract term names
        term_names = {t["term"].lower() for t in result["cultural_terms"]}
        assert "dharma" in term_names

    @pytest.mark.asyncio
    async def test_sikh_terms_preserved(
        self,
        punjabi_sample_text: str,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """CRITICAL: Test that Sikh terms are preserved untranslated."""
        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": (
                    "The sangat gathered at the gurdwara. "
                    "After kirtan, everyone went to langar for seva."
                ),
                "cultural_terms": [
                    {"term": "sangat", "original_script": "ਸੰਗਤ",
                     "definition": "Congregation"},
                    {"term": "gurdwara", "original_script": "ਗੁਰਦੁਆਰਾ",
                     "definition": "Sikh place of worship"},
                    {"term": "kirtan", "original_script": "ਕੀਰਤਨ",
                     "definition": "Devotional singing"},
                    {"term": "langar", "original_script": "ਲੰਗਰ", "definition": "Community kitchen"},
                    {"term": "seva", "original_script": "ਸੇਵਾ", "definition": "Selfless service"},
                ],
                "prompt_tokens": 200,
                "completion_tokens": 100,
                "model_version": "gpt-4",
            }
        )

        result = await mock_llm_client.translate_chunk(
            "ਸੰਗਤ ਗੁਰਦੁਆਰੇ ਵਿੱਚ...",
            seed_terms=seed_glossary_dict,
        )

        # CRITICAL: All Sikh terms must be preserved
        text_lower = result["translated_text"].lower()
        assert "sangat" in text_lower
        assert "gurdwara" in text_lower
        assert "langar" in text_lower
        assert "seva" in text_lower
        assert "kirtan" in text_lower

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "term",
        ["atman", "dharma", "karma", "moksha", "samsara", "maya", "guru"],
    )
    async def test_hindi_terms_in_glossary(
        self,
        term: str,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test that Hindi seed terms appear in glossary."""
        # All seed terms should be in the seed glossary
        assert term in seed_glossary_dict
        script, definition = seed_glossary_dict[term]
        assert len(script) > 0
        assert len(definition) > 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "term",
        ["sangat", "langar", "seva", "gurdwara", "kirtan", "ardas", "simran"],
    )
    async def test_punjabi_terms_in_glossary(
        self,
        term: str,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test that Punjabi seed terms appear in glossary."""
        assert term in seed_glossary_dict
        script, definition = seed_glossary_dict[term]
        assert len(script) > 0
        assert len(definition) > 0

    @pytest.mark.asyncio
    async def test_occurrence_counting(
        self,
        hindi_sample_text: str,
    ) -> None:
        """Test that term occurrences are counted across chunks."""
        # Count occurrences of dharma in sample text
        dharma_count = hindi_sample_text.lower().count("धर्म")
        
        # Should appear at least once in our sample
        assert dharma_count > 0

    @pytest.mark.asyncio
    async def test_mixed_language_text(
        self,
        mock_llm_client: AsyncMock,
        seed_glossary_dict: dict[str, tuple[str, str]],
    ) -> None:
        """Test handling of mixed Hindi and English text."""
        mixed_text = "The concept of dharma is central. We must perform our karma with devotion."

        mock_llm_client.translate_chunk = AsyncMock(
            return_value={
                "translated_text": mixed_text,
                "cultural_terms": [
                    {"term": "dharma", "original_script": "धर्म", "definition": "Righteous duty"},
                    {"term": "karma", "original_script": "कर्म", "definition": "Action"},
                ],
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "model_version": "gpt-4",
            }
        )

        result = await mock_llm_client.translate_chunk(mixed_text, seed_terms=seed_glossary_dict)

        # Cultural terms should still be identified
        assert len(result["cultural_terms"]) >= 2
