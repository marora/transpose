"""Pipeline orchestrator — runs stages in sequence for a book."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from transpose.models.enums import BookStatus, SourceLanguage

logger = logging.getLogger(__name__)


@dataclass
class PipelineInput:
    """Top-level input to run the full pipeline."""

    source_path: str
    title: str
    author: str | None = None
    source_language: SourceLanguage = SourceLanguage.HINDI
    output_formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])
    resume_from: str | None = None


@dataclass
class PipelineOutput:
    """Top-level output of the full pipeline."""

    book_id: UUID
    status: BookStatus
    artifacts: list[dict]
    glossary_term_count: int
    total_tokens_used: int
    stages_completed: list[str]
    errors: list[dict]


STAGE_ORDER = ["ingest", "ocr", "chunk", "translate", "glossary", "assemble", "export"]


async def run_pipeline(input: PipelineInput, ctx=None) -> PipelineOutput:  # type: ignore[no-untyped-def]
    """Execute the full translation pipeline for a book.

    Runs stages sequentially. If resume_from is set, skips stages
    before the specified stage. Each stage is idempotent.
    """
    import logging
    from datetime import datetime

    from transpose.models.enums import BookStatus
    from transpose.observability.metrics import pipeline_errors, stage_duration
    from transpose.services import ServiceContext

    # Import all stage modules
    from . import assemble, chunk, export, glossary, ingest, ocr, translate

    logger = logging.getLogger(__name__)

    # Initialize service context if not provided
    if ctx is None:
        ctx = ServiceContext()
        await ctx.connect()

    stages_completed: list[str] = []
    errors: list[dict] = []
    book_id = None
    artifacts: list[dict] = []
    glossary_term_count = 0
    total_tokens = 0

    # Determine which stages to run
    start_index = 0
    if input.resume_from:
        try:
            start_index = STAGE_ORDER.index(input.resume_from)
            logger.info(f"Resuming from stage: {input.resume_from}")
        except ValueError:
            logger.warning(f"Unknown stage: {input.resume_from}, starting from beginning")

    try:
        # Stage 1: Ingest
        if start_index <= STAGE_ORDER.index("ingest"):
            logger.info("=== Stage 1: Ingest ===")
            start_time = datetime.now()

            ingest_output = await ingest.run(
                ingest.IngestInput(
                    source_path=input.source_path,
                    title=input.title,
                    author=input.author,
                    source_language=input.source_language,
                ),
                ctx,
            )

            book_id = ingest_output.book_id
            await ctx.state.set_pipeline_status(str(book_id), "ingest")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "ingest", "book_id": str(book_id)})
            stages_completed.append("ingest")

            logger.info(
                f"Ingest complete: book_id={book_id}, "
                f"pages={ingest_output.page_count}, "
                f"already_existed={ingest_output.already_existed}"
            )

        # Stage 2: OCR
        if start_index <= STAGE_ORDER.index("ocr"):
            logger.info("=== Stage 2: OCR ===")
            start_time = datetime.now()

            # Need book_id from previous stage or resume
            if not book_id and input.resume_from:
                # For resume, we need to get book_id from somewhere
                # This is a simplification - in production, you'd pass book_id explicitly
                raise ValueError("book_id required for resume_from")

            ocr_output = await ocr.run(ocr.OcrInput(book_id=book_id), ctx)

            await ctx.state.set_pipeline_status(str(book_id), "ocr")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "ocr", "book_id": str(book_id)})
            stages_completed.append("ocr")

            logger.info(
                f"OCR complete: processed={ocr_output.pages_processed}, "
                f"skipped={ocr_output.pages_skipped}, "
                f"low_confidence={ocr_output.low_confidence_count}"
            )

        # Stage 3: Chunk
        if start_index <= STAGE_ORDER.index("chunk"):
            logger.info("=== Stage 3: Chunk ===")
            start_time = datetime.now()

            chunk_output = await chunk.run(chunk.ChunkInput(book_id=book_id), ctx)

            await ctx.state.set_pipeline_status(str(book_id), "chunk")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "chunk", "book_id": str(book_id)})
            stages_completed.append("chunk")

            logger.info(f"Chunk complete: total_chunks={chunk_output.total_chunks}")

        # Stage 4: Translate
        if start_index <= STAGE_ORDER.index("translate"):
            logger.info("=== Stage 4: Translate ===")
            start_time = datetime.now()

            translate_output = await translate.run(
                translate.TranslateInput(book_id=book_id, concurrency=5),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "translate")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "translate", "book_id": str(book_id)})
            stages_completed.append("translate")

            total_tokens = (
                translate_output.total_prompt_tokens + translate_output.total_completion_tokens
            )

            logger.info(
                f"Translate complete: chunks={translate_output.chunks_translated}, "
                f"tokens={total_tokens}"
            )

        # Stage 5: Glossary
        if start_index <= STAGE_ORDER.index("glossary"):
            logger.info("=== Stage 5: Glossary ===")
            start_time = datetime.now()

            glossary_output = await glossary.run(
                glossary.GlossaryInput(book_id=book_id),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "glossary")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "glossary", "book_id": str(book_id)})
            stages_completed.append("glossary")

            glossary_term_count = glossary_output.total_terms

            logger.info(
                f"Glossary complete: terms={glossary_output.total_terms}, "
                f"needs_review={glossary_output.needs_review_count}"
            )

        # Stage 6: Assemble
        if start_index <= STAGE_ORDER.index("assemble"):
            logger.info("=== Stage 6: Assemble ===")
            start_time = datetime.now()

            assemble_output = await assemble.run(
                assemble.AssembleInput(book_id=book_id),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "assemble")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "assemble", "book_id": str(book_id)})
            stages_completed.append("assemble")

            logger.info(f"Assemble complete: chapters={len(assemble_output.chapters)}")

        # Stage 7: Export
        if start_index <= STAGE_ORDER.index("export"):
            logger.info("=== Stage 7: Export ===")
            start_time = datetime.now()

            export_output = await export.run(
                export.ExportInput(book_id=book_id, formats=input.output_formats),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "export")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "export", "book_id": str(book_id)})
            stages_completed.append("export")

            artifacts = [
                {
                    "format": artifact.format,
                    "blob_uri": artifact.blob_uri,
                    "file_size_bytes": artifact.file_size_bytes,
                }
                for artifact in export_output.artifacts
            ]

            logger.info(f"Export complete: artifacts={len(artifacts)}")

        # Release lock
        if book_id:
            await ctx.state.release_lock(str(book_id))

        final_status = BookStatus.EXPORTED

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")

        # Record error
        error_data = {
            "stage": stages_completed[-1] if stages_completed else "unknown",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        errors.append(error_data)

        # Update book status to FAILED
        if book_id:
            from transpose.models.enums import BookStatus

            await ctx.db.update_book_status(book_id, BookStatus.FAILED)
            await ctx.state.release_lock(str(book_id))

            # Record error metric
            pipeline_errors.add(
                1,
                {
                    "stage": error_data["stage"],
                    "error_type": error_data["error_type"],
                    "book_id": str(book_id),
                },
            )

        final_status = BookStatus.FAILED
        raise

    return PipelineOutput(
        book_id=book_id,
        status=final_status,
        artifacts=artifacts,
        glossary_term_count=glossary_term_count,
        total_tokens_used=total_tokens,
        stages_completed=stages_completed,
        errors=errors,
    )

