"""Stage 4: Translate — LLM translation with cultural term preservation."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from transpose.models.enums import TermSource


@dataclass
class TranslateInput:
    book_id: UUID
    force_retranslate: bool = False
    concurrency: int = 5


@dataclass
class ExtractedTerm:
    term: str
    original_script: str
    definition: str
    source: TermSource


@dataclass
class TranslationResult:
    chunk_id: UUID
    translated_text: str
    cultural_terms: list[ExtractedTerm]
    prompt_tokens: int
    completion_tokens: int
    model_version: str


TRANSLATION_FAILED_PLACEHOLDER = "[TRANSLATION FAILED — REVIEW REQUIRED]"


@dataclass
class TranslateOutput:
    book_id: UUID
    chunks_translated: int
    chunks_skipped: int
    total_prompt_tokens: int
    total_completion_tokens: int
    cultural_terms_found: int
    translations: list[TranslationResult] = field(default_factory=list)
    failed_count: int = 0


async def run(input: TranslateInput, ctx) -> TranslateOutput:  # type: ignore[no-untyped-def]
    """Translate all chunks for a book using Azure OpenAI GPT-4o.

    Preserves cultural terms using seed glossary + LLM detection.
    Uses JSON mode for structured output.
    Passes previous chunk context for translation continuity.
    """
    import asyncio
    import logging

    from transpose.config.seed_glossary import get_seed_glossary
    from transpose.models.enums import BookStatus
    from transpose.models.translation import Translation
    from transpose.observability.metrics import (
        chunks_translated,
        content_filter_blocks,
        tokens_used,
        translation_errors,
    )
    from transpose.services.llm_client import TranslationError
    from transpose.utils.unicode import normalize_unicode

    logger = logging.getLogger(__name__)

    # Get book
    book = await ctx.db.get_book(input.book_id)
    if not book:
        raise ValueError(f"Book not found: {input.book_id}")

    logger.info(f"Starting translation for book: {book.title} ({book.id})")

    # Get all chunks
    chunks = await ctx.db.get_chunks_for_book(input.book_id)
    if not chunks:
        raise ValueError(f"No chunks found for book: {input.book_id}")

    logger.info(f"Found {len(chunks)} chunks to translate")

    # Get already-translated chunks (idempotent)
    translated_chunk_ids = await ctx.db.get_translated_chunk_ids(input.book_id)
    logger.info(f"Already translated: {len(translated_chunk_ids)} chunks")

    # Filter chunks to translate
    chunks_to_translate = [
        chunk
        for chunk in chunks
        if input.force_retranslate or chunk.id not in translated_chunk_ids
    ]

    if not chunks_to_translate:
        logger.info("All chunks already translated")
        return TranslateOutput(
            book_id=input.book_id,
            chunks_translated=0,
            chunks_skipped=len(chunks),
            total_prompt_tokens=0,
            total_completion_tokens=0,
            cultural_terms_found=0,
            translations=[],
        )

    logger.info(f"Translating {len(chunks_to_translate)} chunks")

    # Load seed glossary
    seed_terms = get_seed_glossary()
    logger.info(f"Loaded {len(seed_terms)} seed terms")

    # Translate chunks with concurrency control
    semaphore = asyncio.Semaphore(input.concurrency)
    translations: list[TranslationResult] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cultural_terms = 0
    failed_count = 0
    previous_translation = None

    async def translate_chunk(chunk, prev_context: str | None):
        async with semaphore:
            logger.info(f"Translating chunk {chunk.sequence + 1}/{len(chunks)}")

            # Call LLM
            response = await ctx.llm.translate_chunk(
                source_text=chunk.source_text,
                source_language=book.source_language,
                previous_context=prev_context,
                seed_terms=seed_terms,
            )

            # Create translation record
            translation = Translation(
                chunk_id=chunk.id,
                book_id=input.book_id,
                translated_text=response.translated_text,
                model_version=response.model_version,
                cultural_terms=response.cultural_terms,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                raw_response=response.raw_response,
            )

            # Save to database
            await ctx.db.create_translation(translation)

            # Record metrics
            chunks_translated.add(1, {"book_id": str(input.book_id)})
            tokens_used.add(
                response.prompt_tokens + response.completion_tokens,
                {"book_id": str(input.book_id), "type": "translation"},
            )

            return TranslationResult(
                chunk_id=chunk.id,
                translated_text=response.translated_text,
                cultural_terms=[
                    ExtractedTerm(
                        term=term.term,
                        original_script=normalize_unicode(term.original_script),
                        definition=term.definition,
                        source=term.source,
                    )
                    for term in response.cultural_terms
                ],
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                model_version=response.model_version,
            ), response

    # Translate chunks sequentially to maintain context
    for i, chunk in enumerate(chunks_to_translate):
        # Get previous context (last 200 chars of previous translation)
        prev_context = None
        if previous_translation and len(previous_translation.translated_text) > 200:
            prev_context = previous_translation.translated_text[-200:]

        try:
            result, response = await translate_chunk(chunk, prev_context)
            translations.append(result)

            total_prompt_tokens += result.prompt_tokens
            total_completion_tokens += result.completion_tokens
            total_cultural_terms += len(result.cultural_terms)

            previous_translation = response
        except TranslationError as exc:
            error_label = exc.error_type
            if error_label == "content_filter":
                logger.warning(
                    f"Content filter blocked chunk {chunk.id} "
                    f"(sequence {chunk.sequence}): {exc}"
                )
                content_filter_blocks.add(1, {"book_id": str(input.book_id)})
            else:
                logger.warning(
                    f"{error_label.replace('_', ' ').title()} error on chunk {chunk.id} "
                    f"(sequence {chunk.sequence}): {exc}"
                )
            translation_errors.add(
                1, {"book_id": str(input.book_id), "error_type": error_label}
            )
            failed_count += 1

            placeholder = Translation(
                chunk_id=chunk.id,
                book_id=input.book_id,
                translated_text=TRANSLATION_FAILED_PLACEHOLDER,
                model_version="n/a",
                cultural_terms=[],
                prompt_tokens=0,
                completion_tokens=0,
                raw_response={},
                error_type=error_label,
                error_reason=str(exc),
            )
            await ctx.db.create_translation(placeholder)

            translations.append(
                TranslationResult(
                    chunk_id=chunk.id,
                    translated_text=TRANSLATION_FAILED_PLACEHOLDER,
                    cultural_terms=[],
                    prompt_tokens=0,
                    completion_tokens=0,
                    model_version="n/a",
                )
            )
        except Exception as exc:
            logger.warning(
                f"Translation failed for chunk {chunk.id} "
                f"(sequence {chunk.sequence}): {exc}"
            )
            translation_errors.add(
                1, {"book_id": str(input.book_id), "error_type": "unknown"}
            )
            failed_count += 1

            placeholder = Translation(
                chunk_id=chunk.id,
                book_id=input.book_id,
                translated_text=TRANSLATION_FAILED_PLACEHOLDER,
                model_version="n/a",
                cultural_terms=[],
                prompt_tokens=0,
                completion_tokens=0,
                raw_response={},
                error_type="unknown",
                error_reason=str(exc),
            )
            await ctx.db.create_translation(placeholder)

            translations.append(
                TranslationResult(
                    chunk_id=chunk.id,
                    translated_text=TRANSLATION_FAILED_PLACEHOLDER,
                    cultural_terms=[],
                    prompt_tokens=0,
                    completion_tokens=0,
                    model_version="n/a",
                )
            )
            # Don't update previous_translation — keep last successful context

        # Update progress
        await ctx.state.set_progress(
            str(input.book_id),
            "translate",
            i + 1,
            len(chunks_to_translate),
        )

    # Completeness check: every input chunk must have a translation result
    if len(translations) != len(chunks_to_translate):
        raise ValueError(
            f"Translation completeness check failed: "
            f"expected {len(chunks_to_translate)} translations, "
            f"got {len(translations)}"
        )

    # Update book status
    await ctx.db.update_book_status(input.book_id, BookStatus.TRANSLATED)

    logger.info(
        f"Translation complete: {len(translations)} chunks translated, "
        f"{failed_count} failed"
    )

    return TranslateOutput(
        book_id=input.book_id,
        chunks_translated=len(translations),
        chunks_skipped=len(translated_chunk_ids),
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        cultural_terms_found=total_cultural_terms,
        translations=translations,
        failed_count=failed_count,
    )

