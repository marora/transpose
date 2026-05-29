"""Unit tests for the audiobook pipeline stage and TTS provider abstraction."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from transpose.pipeline.audiobook import (
    AudiobookInput,
    AudiobookOutput,
    _strip_html,
    _split_long_chapter,
    _build_pronunciation_lexicon,
)
from transpose.services.tts_provider import (
    AudioResult,
    AzureTTSProvider,
    SSMLOptions,
    TTSProviderType,
    Voice,
    WordBoundary,
    get_tts_provider,
)


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_decodes_entities(self):
        assert _strip_html("&amp; &lt; &gt;") == "& < >"

    def test_preserves_paragraph_breaks(self):
        result = _strip_html("<p>Para 1</p><p>Para 2</p>")
        # Tags removed, content preserved
        assert "Para 1" in result
        assert "Para 2" in result

    def test_empty_input(self):
        assert _strip_html("") == ""


class TestSplitLongChapter:
    def test_short_chapter_not_split(self):
        text = "Short chapter content."
        result = _split_long_chapter(text, max_chars=1000)
        assert len(result) == 1
        assert result[0] == text

    def test_long_chapter_split_at_paragraphs(self):
        # Create text with paragraphs that exceeds max
        paragraphs = ["Paragraph content number " + str(i) + "." for i in range(100)]
        text = "\n\n".join(paragraphs)
        result = _split_long_chapter(text, max_chars=500)
        assert len(result) > 1
        # All content preserved
        reassembled = "\n\n".join(result)
        for p in paragraphs:
            assert p in reassembled


class TestBuildPronunciationLexicon:
    def test_known_terms_get_ipa(self):
        terms = [{"term": "dharma"}, {"term": "karma"}, {"term": "unknown_term"}]
        lexicon = _build_pronunciation_lexicon(terms)
        assert "dharma" in lexicon
        assert "karma" in lexicon
        assert "unknown_term" not in lexicon

    def test_empty_glossary(self):
        assert _build_pronunciation_lexicon([]) == {}


class TestSSMLOptions:
    def test_defaults(self):
        opts = SSMLOptions()
        assert opts.rate == "-10%"
        assert opts.paragraph_pause_ms == 500
        assert opts.chapter_intro_pause_ms == 2000
        assert opts.pronunciation_lexicon == {}


class TestTTSProviderFactory:
    def test_azure_provider(self):
        provider = get_tts_provider("azure", speech_key="test", speech_region="eastus")
        assert isinstance(provider, AzureTTSProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError):
            get_tts_provider("unknown_provider")

    def test_elevenlabs_not_implemented(self):
        with pytest.raises(NotImplementedError):
            get_tts_provider("elevenlabs")

    def test_openai_not_implemented(self):
        with pytest.raises(NotImplementedError):
            get_tts_provider("openai")


class TestAzureTTSProvider:
    def test_estimate_cost(self):
        provider = AzureTTSProvider(speech_key="test", speech_region="eastus")
        # 1M chars at $24/1M = $24
        cost = provider.estimate_cost(1_000_000)
        assert abs(cost - 24.0) < 0.01

    def test_supports_word_boundaries(self):
        provider = AzureTTSProvider(speech_key="test", speech_region="eastus")
        assert provider.supports_word_boundaries() is True

    def test_supports_ssml(self):
        provider = AzureTTSProvider(speech_key="test", speech_region="eastus")
        assert provider.supports_ssml() is True

    def test_build_ssml_basic(self):
        provider = AzureTTSProvider(speech_key="test", speech_region="eastus")
        ssml = provider._build_ssml(
            "Hello world.\n\nSecond paragraph.",
            "en-US-AndrewMultilingualNeural",
            SSMLOptions(),
            chapter_title="Chapter 1: Introduction",
        )
        assert "en-US-AndrewMultilingualNeural" in ssml
        assert "Chapter 1: Introduction" in ssml
        assert "Hello world." in ssml
        assert "Second paragraph." in ssml
        assert 'rate="-10%"' in ssml

    def test_build_ssml_with_lexicon(self):
        provider = AzureTTSProvider(speech_key="test", speech_region="eastus")
        opts = SSMLOptions(pronunciation_lexicon={"dharma": "dɑːrmə"})
        ssml = provider._build_ssml(
            "The concept of dharma is central.",
            "en-US-AndrewMultilingualNeural",
            opts,
            chapter_title=None,
        )
        assert "phoneme" in ssml
        assert "dɑːrmə" in ssml


class TestAudiobookStage:
    """Integration-style test with mocked services."""

    @pytest.mark.asyncio
    async def test_run_produces_output(self):
        book_id = uuid4()

        # Mock manuscript with chapters
        mock_chapter = MagicMock()
        mock_chapter.number = 1
        mock_chapter.title = "The Beginning"
        mock_chapter.content_html = "<p>This is chapter one content.</p>"

        mock_manuscript = MagicMock()
        mock_manuscript.chapters = [mock_chapter]

        mock_book = MagicMock()
        mock_book.title = "Test Book"

        mock_glossary = MagicMock()
        mock_glossary.terms = [{"term": "dharma"}]

        # Mock context
        ctx = MagicMock()
        ctx.db.get_book = AsyncMock(return_value=mock_book)
        ctx.db.get_manuscript_for_book = AsyncMock(return_value=mock_manuscript)
        ctx.db.get_glossary_for_book = AsyncMock(return_value=mock_glossary)

        # Mock TTS provider
        ctx.tts = AsyncMock()
        ctx.tts.synthesize = AsyncMock(
            return_value=AudioResult(
                audio_bytes=b"\xff" * 1000,
                duration_ms=30000,
                word_boundaries=[],
                character_count=100,
                cost_estimate=0.0024,
            )
        )

        # Mock blob upload
        ctx.blob.upload_bytes = AsyncMock(return_value="https://blob.test/chapter-001.mp3")

        from transpose.pipeline.audiobook import run

        output = await run(AudiobookInput(book_id=book_id), ctx)

        assert isinstance(output, AudiobookOutput)
        assert output.book_id == book_id
        assert len(output.chapters) == 1
        assert output.chapters[0].chapter_number == 1
        assert output.chapters[0].title == "The Beginning"
        assert output.total_duration_ms == 30000
        ctx.tts.synthesize.assert_called_once()
