"""Tests for transpose.services.llm_client — Azure OpenAI translation wrapper.

Covers:
- TranslationError class: error_type, source_snippet
- TranslationResponse fields
- Prompt construction (system, user, seed terms, content filter preamble)
- 4-stage content filter fallback (stage 0: preamble, stages 1-3: reframe)
- Retry logic: rate limit, timeout, transient errors
- Clinical reframing: Hindi and Punjabi body-term sanitization
- Chunked summary: sentence-level elision
- chat() method: happy path and errors
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import openai
import pytest

from transpose.models.enums import SourceLanguage
from transpose.services.llm_client import (
    _BODY_PATTERNS_HINDI,
    _BODY_PATTERNS_PUNJABI,
    LlmClient,
    TranslationError,
    TranslationResponse,
)


def _fake_response(status_code: int = 400) -> httpx.Response:
    """Build a minimal httpx.Response for openai exception constructors."""
    return httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://test"))


# ---------------------------------------------------------------------------
# TranslationError
# ---------------------------------------------------------------------------


class TestTranslationError:
    def test_error_type_stored(self) -> None:
        err = TranslationError("content_filter", "blocked", "source text")
        assert err.error_type == "content_filter"

    def test_source_snippet_stored(self) -> None:
        err = TranslationError("content_filter", "blocked", "snippet here")
        assert err.source_snippet == "snippet here"

    def test_message_in_str(self) -> None:
        err = TranslationError("timeout", "timed out after 30s")
        assert "timed out" in str(err)

    def test_default_snippet_empty(self) -> None:
        err = TranslationError("permanent", "bad request")
        assert err.source_snippet == ""

    def test_all_error_types(self) -> None:
        """Verify known error types are accepted."""
        for etype in ("content_filter", "rate_limit", "timeout", "transient", "permanent"):
            err = TranslationError(etype, "msg")
            assert err.error_type == etype


# ---------------------------------------------------------------------------
# TranslationResponse
# ---------------------------------------------------------------------------


class TestTranslationResponse:
    def test_fields(self) -> None:
        resp = TranslationResponse(
            translated_text="Hello",
            cultural_terms=[],
            prompt_tokens=100,
            completion_tokens=50,
            model_version="gpt-4o",
            raw_response={"translated_text": "Hello", "cultural_terms": []},
        )
        assert resp.translated_text == "Hello"
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 50
        assert resp.model_version == "gpt-4o"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    def test_system_prompt_hindi(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        prompt = client._build_system_prompt(SourceLanguage.HINDI, None)
        assert "Hindi" in prompt
        assert "cultural_terms" in prompt

    def test_system_prompt_punjabi(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        prompt = client._build_system_prompt(SourceLanguage.PUNJABI, None)
        assert "Punjabi" in prompt

    def test_system_prompt_with_seed_terms(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        seeds = {"dharma": ("धर्म", "Righteous duty")}
        prompt = client._build_system_prompt(SourceLanguage.HINDI, seeds)
        assert "dharma" in prompt
        assert "धर्म" in prompt
        assert "Righteous duty" in prompt

    def test_system_prompt_content_filter_preamble(self) -> None:
        """Stage 0: content_filter_context=True prepends scholarly preamble."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        prompt = client._build_system_prompt(
            SourceLanguage.HINDI, None, content_filter_context=True
        )
        assert "IMPORTANT CONTEXT" in prompt
        assert "cultural heritage" in prompt.lower()

    def test_system_prompt_no_preamble_by_default(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        prompt = client._build_system_prompt(
            SourceLanguage.HINDI, None, content_filter_context=False
        )
        assert "IMPORTANT CONTEXT FOR THIS SESSION" not in prompt

    def test_user_prompt_without_context(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        prompt = client._build_user_prompt("धर्म", None)
        assert "धर्म" in prompt
        assert "continuity" not in prompt

    def test_user_prompt_with_previous_context(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        prompt = client._build_user_prompt("धर्म", "previous translation text")
        assert "previous translation text" in prompt
        assert "continuity" in prompt


# ---------------------------------------------------------------------------
# Content filter fallback stages 1-3
# ---------------------------------------------------------------------------


class TestContentFilterFallbackStages:
    """The 3 reframe methods (stages 1-3) after the initial preamble (stage 0)."""

    def test_stage1_reframe_scholarly(self) -> None:
        """Stage 1: scholarly reframing includes academic context."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        result = client._reframe_for_content_filter("योनि शक्ति")
        assert "SCHOLARLY TRANSLATION" in result
        assert "Penguin Classics" in result
        assert "योनि शक्ति" in result

    def test_stage1_with_previous_context(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        result = client._reframe_for_content_filter("text", "previous chunk")
        assert "previous chunk" in result

    def test_stage2_clinical_hindi(self) -> None:
        """Stage 2: Hindi body terms are sanitized."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        text_with_body_term = "कुंडलिनी शक्ति जागृत हुई"
        result = client._reframe_clinical(text_with_body_term, SourceLanguage.HINDI)
        assert "CLINICAL" in result
        assert "[dormant spiritual energy]" in result

    def test_stage2_clinical_punjabi(self) -> None:
        """Stage 2: Punjabi body terms are sanitized."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        text = "ਕੁੰਡਲਨੀ ਸ਼ਕਤੀ"
        result = client._reframe_clinical(text, SourceLanguage.PUNJABI)
        assert "[dormant spiritual energy]" in result

    def test_stage2_non_trigger_text_preserved(self) -> None:
        """Text without trigger terms passes through untouched."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        safe_text = "गीता में कहा गया है"
        result = client._reframe_clinical(safe_text, SourceLanguage.HINDI)
        assert "गीता में कहा गया है" in result

    def test_stage3_chunked_summary_elides_triggers(self) -> None:
        """Stage 3: sentences with trigger terms are replaced with scholarly paraphrases."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        text = "गीता सत्य है। कुंडलिनी जागृत होती है। धर्म महान है।"
        result = client._reframe_chunked_summary(text, SourceLanguage.HINDI)
        assert "scholarly paraphrase" in result
        # The safe sentences should still be present
        assert "गीता सत्य है" in result
        assert "धर्म महान है" in result

    def test_stage3_no_triggers_no_elision(self) -> None:
        """If no trigger terms, no sentences are replaced."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        text = "धर्म महान है। कर्म शुद्ध रखो।"
        result = client._reframe_chunked_summary(text, SourceLanguage.HINDI)
        # The original sentences should be present verbatim
        assert "धर्म महान है" in result
        assert "कर्म शुद्ध रखो" in result
        assert "0 sentence(s)" in result


# ---------------------------------------------------------------------------
# Body pattern coverage
# ---------------------------------------------------------------------------


class TestBodyPatterns:
    def test_hindi_patterns_are_valid_regex(self) -> None:
        for pattern, _replacement in _BODY_PATTERNS_HINDI:
            re.compile(pattern)  # should not raise

    def test_punjabi_patterns_are_valid_regex(self) -> None:
        for pattern, _replacement in _BODY_PATTERNS_PUNJABI:
            re.compile(pattern)  # should not raise

    def test_hindi_pattern_count(self) -> None:
        """Verify we have the expected number of Hindi patterns."""
        assert len(_BODY_PATTERNS_HINDI) >= 15

    def test_punjabi_pattern_count(self) -> None:
        assert len(_BODY_PATTERNS_PUNJABI) >= 10


# ---------------------------------------------------------------------------
# translate_chunk — happy path (mocked SDK)
# ---------------------------------------------------------------------------


def _mock_completion(text: str, prompt_tokens: int = 100, completion_tokens: int = 50):
    """Build a mock ChatCompletion response."""
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        ),
        model="gpt-4o",
    )


class TestTranslateChunkHappyPath:
    @pytest.mark.asyncio
    async def test_returns_translation_response(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=_mock_completion(
                json.dumps({
                    "translated_text": "Righteousness prevails",
                    "cultural_terms": [
                        {
                            "term": "dharma",
                            "original_script": "धर्म",
                            "definition": "Righteous duty",
                            "source": "seed",
                        }
                    ],
                })
            )
        )
        client._client = mock_openai

        resp = await client.translate_chunk(
            "धर्म की जय हो", SourceLanguage.HINDI
        )

        assert isinstance(resp, TranslationResponse)
        assert resp.translated_text == "Righteousness prevails"
        assert len(resp.cultural_terms) == 1
        assert resp.cultural_terms[0].term == "dharma"
        assert resp.prompt_tokens == 100
        assert resp.completion_tokens == 50

    @pytest.mark.asyncio
    async def test_empty_response_raises(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
                usage=None,
                model="gpt-4o",
            )
        )
        client._client = mock_openai

        with pytest.raises(ValueError, match="Empty response"):
            await client.translate_chunk("text", SourceLanguage.HINDI)


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_rate_limit_retries_then_raises(self) -> None:
        """RateLimitError retries 3 times then raises TranslationError."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="rate limited",
                response=_fake_response(429),
                body=None,
            )
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.translate_chunk("text", SourceLanguage.HINDI)
        assert exc_info.value.error_type == "rate_limit"

    @pytest.mark.asyncio
    async def test_timeout_retries_then_raises(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=openai.APITimeoutError(request=httpx.Request("POST", "https://test"))
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.translate_chunk("text", SourceLanguage.HINDI)
        assert exc_info.value.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_transient_api_error_retries(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=openai.APIError(
                message="server error",
                request=httpx.Request("POST", "https://test"),
                body=None,
            )
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.translate_chunk("text", SourceLanguage.HINDI)
        assert exc_info.value.error_type == "transient"

    @pytest.mark.asyncio
    async def test_permanent_error_no_retry(self) -> None:
        """Non-retryable exceptions raise immediately as permanent."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("unexpected")
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.translate_chunk("text", SourceLanguage.HINDI)
        assert exc_info.value.error_type == "permanent"


# ---------------------------------------------------------------------------
# Content filter fallback chain (integration of stages 0-3)
# ---------------------------------------------------------------------------


class TestContentFilterFallbackChain:
    """Verify the full 4-stage fallback when content filter fires."""

    @pytest.mark.asyncio
    async def test_fallback_stage1_succeeds(self) -> None:
        """Content filter on initial call → stage 1 reframe succeeds."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        good_response = _mock_completion(
            json.dumps({"translated_text": "recovered", "cultural_terms": []})
        )

        mock_openai = AsyncMock()
        # First call: content filter, second call (stage 1): success
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=[
                openai.BadRequestError(
                    message="content_filter triggered",
                    response=_fake_response(400),
                    body=None,
                ),
                good_response,
            ]
        )
        client._client = mock_openai

        resp = await client.translate_chunk("कुंडलिनी text", SourceLanguage.HINDI)
        assert resp.translated_text == "recovered"

    @pytest.mark.asyncio
    async def test_fallback_all_stages_fail(self) -> None:
        """All stages fail → TranslationError with content_filter type."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        filter_error = openai.BadRequestError(
            message="content_filter",
            response=_fake_response(400),
            body=None,
        )

        mock_openai = AsyncMock()
        # Initial + 3 fallback stages = 4 BadRequestErrors
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=[filter_error, filter_error, filter_error, filter_error]
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.translate_chunk("trigger text", SourceLanguage.HINDI)
        assert exc_info.value.error_type == "content_filter"
        assert exc_info.value.source_snippet != ""

    @pytest.mark.asyncio
    async def test_fallback_stage2_succeeds(self) -> None:
        """Stage 1 fails, stage 2 (clinical) succeeds."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        filter_error = openai.BadRequestError(
            message="content_filter",
            response=_fake_response(400),
            body=None,
        )
        good_response = _mock_completion(
            json.dumps({"translated_text": "clinical recovery", "cultural_terms": []})
        )

        mock_openai = AsyncMock()
        # Initial: filter, stage 1: filter, stage 2: success
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=[filter_error, filter_error, good_response]
        )
        client._client = mock_openai

        resp = await client.translate_chunk("text", SourceLanguage.HINDI)
        assert resp.translated_text == "clinical recovery"

    @pytest.mark.asyncio
    async def test_non_content_filter_bad_request_is_permanent(self) -> None:
        """BadRequestError that isn't content_filter → permanent error."""
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=openai.BadRequestError(
                message="invalid model parameter",
                response=_fake_response(400),
                body=None,
            )
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.translate_chunk("text", SourceLanguage.HINDI)
        assert exc_info.value.error_type == "permanent"


# ---------------------------------------------------------------------------
# chat() method
# ---------------------------------------------------------------------------


class TestChatMethod:
    @pytest.mark.asyncio
    async def test_chat_happy_path(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="  Generated foreword  ")
                    )
                ],
            )
        )
        client._client = mock_openai

        result = await client.chat("Write a foreword")
        assert result == "Generated foreword"  # stripped

    @pytest.mark.asyncio
    async def test_chat_empty_response_raises(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            return_value=SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
            )
        )
        client._client = mock_openai

        with pytest.raises(ValueError, match="Empty response"):
            await client.chat("prompt")

    @pytest.mark.asyncio
    async def test_chat_content_filter_raises(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=openai.BadRequestError(
                message="content_filter",
                response=_fake_response(400),
                body=None,
            )
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.chat("blocked prompt")
        assert exc_info.value.error_type == "content_filter"

    @pytest.mark.asyncio
    async def test_chat_rate_limit(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")

        mock_openai = AsyncMock()
        mock_openai.chat.completions.create = AsyncMock(
            side_effect=openai.RateLimitError(
                message="rate limited",
                response=_fake_response(429),
                body=None,
            )
        )
        client._client = mock_openai

        with pytest.raises(TranslationError) as exc_info:
            await client.chat("prompt")
        assert exc_info.value.error_type == "rate_limit"


# ---------------------------------------------------------------------------
# client configuration + readiness
# ---------------------------------------------------------------------------


class TestLlmClientConfiguration:
    @pytest.mark.asyncio
    async def test_get_client_uses_configured_timeout(self) -> None:
        client = LlmClient(
            "https://oai.azure.com",
            "gpt-4o",
            "2024-10-21",
            timeout_seconds=180.0,
        )

        with (
            patch("azure.identity.aio.DefaultAzureCredential"),
            patch("azure.identity.aio.get_bearer_token_provider", return_value="token-provider"),
            patch("openai.AsyncAzureOpenAI") as mock_openai,
        ):
            mock_openai.return_value = AsyncMock()
            await client._get_client()

        timeout = mock_openai.call_args.kwargs["timeout"]
        assert timeout.read == 180.0
        assert timeout.connect == 10.0

    @pytest.mark.asyncio
    async def test_health_check_initializes_client(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        client._get_client = AsyncMock(return_value=AsyncMock())

        await client.health_check()

        client._get_client.assert_awaited_once()


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestLlmClientClose:
    @pytest.mark.asyncio
    async def test_close_when_initialized(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        mock_openai = AsyncMock()
        client._client = mock_openai
        await client.close()
        mock_openai.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self) -> None:
        client = LlmClient("https://oai.azure.com", "gpt-4o", "2024-10-21")
        await client.close()  # should not raise
