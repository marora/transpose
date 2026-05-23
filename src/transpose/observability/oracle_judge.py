"""Oracle Layer C — Anthropic Claude Sonnet 4.5 quality judge.

Post-export, non-blocking translation quality assessment on a stratified 5% sample.
Complements Layer A (LaBSE embeddings) with cross-family LLM judgment to reduce
self-preference bias.

Fires asynchronously after the export stage completes. Errors are logged but never
block the pipeline. Results written to book_validation_reports.oracle_score.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID

    from transpose.models.translation import Chunk, Translation

logger = logging.getLogger(__name__)


@dataclass
class OracleScore:
    """Oracle Layer C quality score payload."""

    composite_score: int  # 0–100 overall score
    fluency: int  # 0–100 naturalness of English prose
    cultural_register: int  # 0–100 accuracy of cultural/spiritual terminology
    terminology_nuance: int  # 0–100 preservation of source language semantic richness
    sampled_chunk_ids: list[str]  # UUIDs of chunks assessed
    raw_judge_response: str  # Full JSON from Anthropic API


def select_stratified_sample(
    chunks: list[Chunk],
    sample_fraction: float = 0.05,
) -> list[Chunk]:
    """Select a stratified 5% sample of chunks from early/mid/late sections.

    Divides chunks into three equal bins (early/mid/late) and samples from each
    to ensure representative coverage. If total sample size is not evenly divisible
    by 3, the remainder is allocated to the early bin.

    Args:
        chunks: All chunks for the book, ordered by sequence.
        sample_fraction: Fraction of chunks to sample (default 0.05 = 5%).

    Returns:
        List of sampled chunks (minimum 1, even for very small books).
    """
    if not chunks:
        return []

    total = len(chunks)
    target_count = max(1, int(total * sample_fraction))

    # For very small chunk lists, just sample directly
    if total <= 3:
        import random

        # Return all chunks if target >= total, else sample randomly
        if target_count >= total:
            return chunks
        return random.sample(chunks, target_count)

    # Split into three bins: early, mid, late
    third = total // 3
    early = chunks[:third]
    mid = chunks[third : 2 * third]
    late = chunks[2 * third :]

    # Distribute sample across bins
    per_bin = target_count // 3
    remainder = target_count % 3

    import random

    sample = []

    # Early bin gets the remainder
    if early:
        sample.extend(random.sample(early, min(per_bin + remainder, len(early))))
    if mid:
        sample.extend(random.sample(mid, min(per_bin, len(mid))))
    if late:
        sample.extend(random.sample(late, min(per_bin, len(late))))

    # Ensure we got at least 1 chunk
    if not sample and chunks:
        sample = [random.choice(chunks)]

    # Sort by sequence to maintain document order
    sample.sort(key=lambda c: c.sequence)
    return sample


async def judge_translation_quality(
    book_id: UUID,
    chunks: list[Chunk],
    translations: list[Translation],
    anthropic_api_key: str,
    sample_fraction: float = 0.05,
) -> OracleScore | None:
    """Run Layer C quality assessment using Anthropic Claude Sonnet 4.5 judge.

    Selects a stratified 5% sample, sends source + translation pairs to the judge,
    and returns structured quality metrics.

    Args:
        book_id: Book being assessed.
        chunks: All chunks for the book.
        translations: All translations for the book.
        anthropic_api_key: Anthropic API key (from Key Vault or .env).
        sample_fraction: Fraction of chunks to sample (default 0.05).

    Returns:
        OracleScore payload, or None if the judge call fails.
    """
    if not anthropic_api_key:
        logger.warning(
            "Oracle Layer C skipped: TRANSPOSE_ANTHROPIC_API_KEY not configured "
            "(book_id=%s)",
            book_id,
        )
        return None

    if not chunks or not translations:
        logger.warning(
            "Oracle Layer C skipped: no chunks or translations (book_id=%s)",
            book_id,
        )
        return None

    # Select stratified sample
    sampled_chunks = select_stratified_sample(chunks, sample_fraction)
    if not sampled_chunks:
        logger.warning(
            "Oracle Layer C skipped: no chunks sampled (book_id=%s)",
            book_id,
        )
        return None

    logger.info(
        "Oracle Layer C: sampling %d/%d chunks (%.1f%%) for book_id=%s",
        len(sampled_chunks),
        len(chunks),
        100 * len(sampled_chunks) / len(chunks),
        book_id,
    )

    # Build chunk_id → translation map
    translation_map = {t.chunk_id: t for t in translations}

    # Prepare judge payload
    samples = []
    for chunk in sampled_chunks:
        translation = translation_map.get(chunk.id)
        if not translation:
            logger.debug(
                "Oracle Layer C: chunk %s has no translation, skipping", chunk.id
            )
            continue
        samples.append(
            {
                "chunk_id": str(chunk.id),
                "source_text": chunk.source_text,
                "translated_text": translation.translated_text,
            }
        )

    if not samples:
        logger.warning(
            "Oracle Layer C skipped: no valid sample pairs (book_id=%s)",
            book_id,
        )
        return None

    # Call Anthropic API
    try:
        judge_response = await _call_anthropic_judge(samples, anthropic_api_key)
    except Exception as exc:
        logger.error(
            "Oracle Layer C failed: Anthropic API error (book_id=%s): %s",
            book_id,
            exc,
            exc_info=True,
        )
        return None

    # Parse response
    try:
        result = json.loads(judge_response)
        return OracleScore(
            composite_score=result["composite_score"],
            fluency=result["fluency"],
            cultural_register=result["cultural_register"],
            terminology_nuance=result["terminology_nuance"],
            sampled_chunk_ids=[s["chunk_id"] for s in samples],
            raw_judge_response=judge_response,
        )
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.error(
            "Oracle Layer C failed: invalid judge response (book_id=%s): %s",
            book_id,
            exc,
        )
        return None


async def _call_anthropic_judge(
    samples: list[dict],
    api_key: str,
    model: str = "claude-sonnet-4-5-20250514",
    timeout: float = 120.0,
) -> str:
    """Call Anthropic API with stratified sample for quality assessment.

    Args:
        samples: List of {chunk_id, source_text, translated_text} dicts.
        api_key: Anthropic API key.
        model: Model name (default: claude-sonnet-4-5-20250514).
        timeout: Request timeout in seconds.

    Returns:
        Raw JSON response string from the judge.
    """
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)

    # Build judge prompt
    system_prompt = _build_judge_system_prompt()
    user_prompt = _build_judge_user_prompt(samples)

    # Call API
    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.0,  # Deterministic scoring
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract text from response
    content_blocks = response.content
    if not content_blocks:
        raise ValueError("Anthropic API returned empty content")

    # Anthropic returns a list of content blocks; take the first text block
    text_content = next(
        (block.text for block in content_blocks if hasattr(block, "text")),
        None,
    )
    if not text_content:
        raise ValueError("Anthropic API response has no text content")

    return text_content


def _build_judge_system_prompt() -> str:
    """Build the system prompt for the Anthropic judge."""
    return """You are a translation quality expert assessing Hindi-to-English translations of classical Indian spiritual and philosophical literature.

Your task: evaluate translation quality on four dimensions:
1. **Fluency** (0–100): Naturalness and readability of English prose
2. **Cultural Register** (0–100): Accuracy of cultural/spiritual terminology preservation
3. **Terminology Nuance** (0–100): Preservation of source language semantic richness
4. **Composite Score** (0–100): Overall quality (weighted average)

Guidelines:
- Cultural terms (Sanskrit, Hindi, Punjabi) should be transliterated and explained, not replaced
- Spiritual/yogic vocabulary requires scholarly precision (e.g., "prana" → vital breath, not "air")
- Fluency matters, but never at the expense of cultural accuracy
- Composite score weights: fluency 30%, cultural register 40%, terminology nuance 30%

Output format (JSON only, no commentary):
{
  "composite_score": 0-100,
  "fluency": 0-100,
  "cultural_register": 0-100,
  "terminology_nuance": 0-100
}"""


def _build_judge_user_prompt(samples: list[dict]) -> str:
    """Build the user prompt for the Anthropic judge.

    Args:
        samples: List of {chunk_id, source_text, translated_text} dicts.

    Returns:
        Formatted prompt string.
    """
    prompt_lines = [
        "Assess the following translation samples from a spiritual text.\n",
        f"Total samples: {len(samples)}\n",
        "---\n",
    ]

    for i, sample in enumerate(samples, 1):
        prompt_lines.append(f"Sample {i}:\n")
        prompt_lines.append(f"Source (Hindi): {sample['source_text'][:500]}...\n")
        prompt_lines.append(
            f"Translation (English): {sample['translated_text'][:500]}...\n"
        )
        prompt_lines.append("---\n")

    prompt_lines.append(
        "\nProvide your assessment as JSON with the four scores (composite_score, fluency, "
        "cultural_register, terminology_nuance)."
    )

    return "".join(prompt_lines)
