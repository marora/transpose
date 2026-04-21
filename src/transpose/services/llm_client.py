"""Azure OpenAI client wrapper for literary translation."""

from __future__ import annotations

import asyncio
import logging

import httpx
import openai

from transpose.models.enums import SourceLanguage
from transpose.models.translation import ExtractedTerm

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


class TranslationError(Exception):
    """Classified translation error with retry semantics."""

    def __init__(
        self,
        error_type: str,
        message: str,
        source_snippet: str = "",
    ) -> None:
        self.error_type = error_type  # content_filter | rate_limit | timeout | transient | permanent
        self.source_snippet = source_snippet
        super().__init__(message)


class LlmClient:
    """Wraps Azure OpenAI for translation calls.

    Handles prompt construction, structured output parsing,
    retry logic, and token tracking. Pipeline stages call this
    interface — never the OpenAI SDK directly.
    """

    def __init__(self, endpoint: str, deployment: str, api_version: str) -> None:
        self._endpoint = endpoint
        self._deployment = deployment
        self._api_version = api_version
        self._client = None

    async def _get_client(self):
        """Lazy-initialize the Azure OpenAI client with Managed Identity."""
        if self._client is None:
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider
            from openai import AsyncAzureOpenAI

            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._endpoint,
                azure_deployment=self._deployment,
                api_version=self._api_version,
                azure_ad_token_provider=token_provider,
                timeout=httpx.Timeout(30.0, connect=10.0),
            )
        return self._client

    async def translate_chunk(
        self,
        source_text: str,
        source_language: SourceLanguage,
        previous_context: str | None = None,
        seed_terms: dict[str, tuple[str, str]] | None = None,
    ) -> TranslationResponse:
        """Translate a chunk of text, preserving cultural terms.

        Args:
            source_text: Source language text to translate.
            source_language: Hindi or Punjabi.
            previous_context: Tail of the previous chunk's translation for continuity.
            seed_terms: Known cultural terms {term: (script, definition)}.

        Returns:
            Structured translation response with text and extracted terms.
        """
        import json

        from transpose.models.enums import TermSource

        client = await self._get_client()

        # Build prompts
        system_prompt = self._build_system_prompt(source_language, seed_terms)
        user_prompt = self._build_user_prompt(source_text, previous_context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        async def _call_with_retry():
            for attempt in range(_MAX_RETRIES):
                try:
                    return await client.chat.completions.create(
                        model=self._deployment,
                        messages=messages,
                        response_format={"type": "json_object"},
                        temperature=0.3,
                    )
                except openai.BadRequestError as e:
                    if "content_filter" in str(e).lower() or getattr(e, "code", "") == "content_filter":
                        # Try academic reframing once on the first attempt
                        if attempt == 0:
                            logger.warning("Content filter hit — attempting academic reframing fallback")
                            reframed_prompt = self._reframe_for_content_filter(source_text, previous_context)
                            try:
                                return await client.chat.completions.create(
                                    model=self._deployment,
                                    messages=[
                                        {"role": "system", "content": system_prompt},
                                        {"role": "user", "content": reframed_prompt},
                                    ],
                                    response_format={"type": "json_object"},
                                    temperature=0.3,
                                )
                            except Exception:
                                pass
                        raise TranslationError("content_filter", str(e), source_text[:100])
                    raise TranslationError("permanent", str(e))
                except openai.RateLimitError:
                    if attempt < _MAX_RETRIES - 1:
                        wait = 2 ** attempt * 2
                        logger.info(f"Rate limited — retrying in {wait}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait)
                        continue
                    raise TranslationError("rate_limit", "Rate limit exceeded after retries")
                except openai.APITimeoutError:
                    if attempt < _MAX_RETRIES - 1:
                        wait = 2 ** attempt
                        logger.info(f"API timeout — retrying in {wait}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait)
                        continue
                    raise TranslationError("timeout", "API timeout after retries")
                except openai.APIError as e:
                    if attempt < _MAX_RETRIES - 1:
                        wait = 2 ** attempt
                        logger.info(f"Transient API error — retrying in {wait}s (attempt {attempt + 1})")
                        await asyncio.sleep(wait)
                        continue
                    raise TranslationError("transient", str(e))
                except Exception as e:
                    raise TranslationError("permanent", str(e))
            raise TranslationError("transient", "Exhausted retries")  # pragma: no cover

        # Make the API call with retry
        response = await _call_with_retry()

        # Parse the structured JSON response
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from LLM")

        parsed = json.loads(content)

        # Extract translation and cultural terms
        translated_text = parsed.get("translated_text", "")
        cultural_terms_data = parsed.get("cultural_terms", [])

        # Convert to ExtractedTerm objects
        cultural_terms = []
        for term_data in cultural_terms_data:
            cultural_terms.append(
                ExtractedTerm(
                    term=term_data.get("term", ""),
                    original_script=term_data.get("original_script", ""),
                    definition=term_data.get("definition", ""),
                    source=TermSource(term_data.get("source", "llm_detected")),
                )
            )

        # Track token usage
        prompt_tokens = response.usage.prompt_tokens if response.usage else 0
        completion_tokens = response.usage.completion_tokens if response.usage else 0

        # Get model version from response
        model_version = response.model

        return TranslationResponse(
            translated_text=translated_text,
            cultural_terms=cultural_terms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_version=model_version,
            raw_response=parsed,
        )

    def _reframe_for_content_filter(
        self, source_text: str, previous_context: str | None = None
    ) -> str:
        """Wrap source text with academic context to reduce content-filter false positives."""
        preamble = (
            "The following is an excerpt from a classical philosophical and spiritual text "
            "being translated for an academic publishing project. The content is scholarly "
            "in nature, covering Indian philosophy, yoga, and meditation traditions. "
            "Please translate this academic excerpt:\n\n"
        )
        prompt = ""
        if previous_context:
            prompt += (
                f"For translation continuity, here is the ending of the previous chunk:\n"
                f"---\n{previous_context}\n---\n\n"
            )
        prompt += preamble + source_text
        prompt += "\n\nRemember to output valid JSON with both translated_text and cultural_terms fields."
        return prompt

    def _build_system_prompt(
        self,
        source_language: SourceLanguage,
        seed_terms: dict[str, tuple[str, str]] | None,
    ) -> str:
        """Build the system prompt for translation."""
        lang_name = "Hindi" if source_language == SourceLanguage.HINDI else "Punjabi"

        prompt = f"""You are a literary translator specializing in {lang_name} to \
English translation.

CONTEXT: This is an academic translation project for preserving classical philosophical \
and spiritual literature. The source texts are scholarly works covering Indian philosophy, \
yoga, and meditation traditions — similar to academic texts published by university presses. \
All content is educational and culturally significant. Approach this work as a scholarly \
translation exercise.

Your task is to produce a fluent, readable English translation that preserves the \
literary style and cultural context.

CRITICAL RULES:
1. Preserve cultural and spiritual terms in their transliterated form (e.g., dharma, karma, guru).
2. For preserved terms, provide the original script and a brief definition.
3. Maintain narrative flow and literary tone — this is not a word-for-word translation.
4. Keep sentence structure natural in English while preserving the meaning and tone of the original.

CULTURAL TERMS:
- Known terms that MUST be preserved (with their original script and definitions):
"""

        if seed_terms:
            for term, (script, definition) in seed_terms.items():
                prompt += f"  - {term} ({script}): {definition}\n"

        prompt += """
- Additionally, identify and preserve any NEW cultural, spiritual, or philosophical \
terms you encounter that don't have direct English equivalents.

OUTPUT FORMAT:
Return a JSON object with this exact structure:
{
  "translated_text": "The translated text in English...",
  "cultural_terms": [
    {
      "term": "transliterated_term",
      "original_script": "original script",
      "definition": "brief English definition",
      "source": "seed" or "llm_detected"
    }
  ]
}

Include ALL cultural terms that appear in this chunk (both from the seed list and newly detected).
"""
        return prompt

    def _build_user_prompt(self, source_text: str, previous_context: str | None) -> str:
        """Build the user prompt for a specific chunk."""
        prompt = ""

        if previous_context:
            prompt += f"""For translation continuity, here is the ending of the previous chunk:
---
{previous_context}
---

"""

        prompt += f"""Translate the following text to English:

{source_text}

Remember to output valid JSON with both translated_text and cultural_terms fields."""

        return prompt

    async def chat(self, prompt: str, *, temperature: float = 0.4) -> str:
        """Send a freeform prompt and return the text response.

        Used for non-translation tasks like foreword generation.
        """
        client = await self._get_client()

        async def _call():
            for attempt in range(_MAX_RETRIES):
                try:
                    return await client.chat.completions.create(
                        model=self._deployment,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                    )
                except openai.BadRequestError as e:
                    if "content_filter" in str(e).lower() or getattr(e, "code", "") == "content_filter":
                        raise TranslationError("content_filter", str(e))
                    raise TranslationError("permanent", str(e))
                except openai.RateLimitError:
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt * 2)
                        continue
                    raise TranslationError("rate_limit", "Rate limit exceeded after retries")
                except openai.APITimeoutError:
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise TranslationError("timeout", "API timeout after retries")
                except openai.APIError as e:
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise TranslationError("transient", str(e))
                except Exception as e:
                    raise TranslationError("permanent", str(e))
            raise TranslationError("transient", "Exhausted retries")  # pragma: no cover

        response = await _call()
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from LLM")
        return content.strip()

    async def close(self) -> None:
        """Release SDK resources."""
        if self._client is not None:
            await self._client.close()


class TranslationResponse:
    """Structured response from a translation call."""

    def __init__(
        self,
        translated_text: str,
        cultural_terms: list[ExtractedTerm],
        prompt_tokens: int,
        completion_tokens: int,
        model_version: str,
        raw_response: dict,
    ) -> None:
        self.translated_text = translated_text
        self.cultural_terms = cultural_terms
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.model_version = model_version
        self.raw_response = raw_response
