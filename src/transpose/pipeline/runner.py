"""Pipeline orchestrator — runs stages in sequence for a book.

Quality gates run between stages and block progression on failure.
A validation report is written to the output directory after export.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from transpose.models.enums import BookStatus, SourceLanguage
from transpose.pipeline.gates import (
    GateResult,
    QualityGateError,
    artifact_availability_gate,
    document_structure_gate,
    glossary_integrity_gate,
    golden_targeted_qa_gate,
    ocr_sanity_gate,
    translation_completeness_gate,
    validate_production_readiness,
)

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
    blob_uri: str | None = None
    output_dir: str | None = None


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
    gate_results: list[dict] = field(default_factory=list)


STAGE_ORDER = ["ingest", "ocr", "chunk", "translate", "glossary", "assemble", "export"]


def _run_gate(gate_fn, gate_input, gate_results: list[GateResult]) -> GateResult:
    """Execute a quality gate, log the result, and raise on failure."""
    result = gate_fn(gate_input)
    gate_results.append(result)

    if result.passed:
        logger.info("✅ Gate '%s' PASSED", result.gate_name)
    else:
        logger.error(
            "❌ Gate '%s' FAILED: %s",
            result.gate_name,
            "; ".join(result.failures),
        )
        raise QualityGateError(result)

    return result


def _build_validation_report(
    book_id: UUID | None,
    gate_results: list[GateResult],
    artifacts: list[dict],
) -> dict:
    """Build the JSON validation report from collected gate results."""
    overall = "PASS" if all(g.passed for g in gate_results) else "FAIL"

    artifact_map = {}
    for a in artifacts:
        artifact_map[a["format"]] = {
            "path": a.get("blob_uri", ""),
            "size_bytes": a.get("file_size_bytes", 0),
            "url": a.get("blob_uri", ""),
        }

    return {
        "book_id": str(book_id) if book_id else None,
        "timestamp": datetime.now(UTC).isoformat(),
        "gates": [
            {
                "name": g.gate_name,
                "passed": g.passed,
                "failures": g.failures,
                "details": g.details,
                "timestamp": g.timestamp,
            }
            for g in gate_results
        ],
        "overall": overall,
        "artifacts": artifact_map,
    }


async def run_pipeline(input: PipelineInput, ctx=None) -> PipelineOutput:  # type: ignore[no-untyped-def]
    """Execute the full translation pipeline for a book.

    Runs stages sequentially with quality gates between them.
    If resume_from is set, skips stages before the specified stage.
    Each stage is idempotent.
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
    gate_results: list[GateResult] = []
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
                    blob_uri=input.blob_uri,
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

            # Quality Gate: OCR Sanity
            _run_gate(ocr_sanity_gate, ocr_output, gate_results)

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

            # Quality Gate: Translation Completeness
            _run_gate(translation_completeness_gate, translate_output, gate_results)

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

            # Quality Gate: Glossary Integrity
            _run_gate(glossary_integrity_gate, glossary_output, gate_results)

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

            # Quality Gate: Document Structure
            # Build a lightweight manuscript-like object from assemble_output
            _run_gate(document_structure_gate, assemble_output, gate_results)

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

            # Quality Gate: Artifact Availability
            _run_gate(artifact_availability_gate, export_output, gate_results)

            # Quality Gate: Golden-Targeted QA (runs after all other gates)
            # Find the PDF artifact path for golden comparison
            pdf_artifact_path = None
            for artifact in export_output.artifacts:
                if getattr(artifact, "format", "") == "pdf":
                    blob_uri = getattr(artifact, "blob_uri", "")
                    if blob_uri:
                        import urllib.parse

                        if blob_uri.startswith("file://"):
                            parsed = urllib.parse.urlparse(blob_uri)
                            pdf_artifact_path = urllib.parse.unquote(parsed.path)
                        elif blob_uri.startswith("/") or (
                            len(blob_uri) > 2 and blob_uri[1] == ":"
                        ):
                            pdf_artifact_path = blob_uri
                    break

            if pdf_artifact_path:
                _run_gate(
                    lambda _inp: golden_targeted_qa_gate(pdf_artifact_path),
                    None,
                    gate_results,
                )

                # --- Gate 7: Production Readiness ---
                _run_gate(
                    lambda _inp: validate_production_readiness(pdf_artifact_path),
                    None,
                    gate_results,
                )

        # Write validation report
        report = _build_validation_report(book_id, gate_results, artifacts)
        if input.output_dir:
            report_path = Path(input.output_dir) / "validation-report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, default=str))
            logger.info("Validation report written to %s", report_path)

        # Release lock
        if book_id:
            await ctx.state.release_lock(str(book_id))

        final_status = BookStatus.EXPORTED

    except QualityGateError as e:
        logger.error("Pipeline halted by quality gate: %s", e)

        error_data = {
            "stage": stages_completed[-1] if stages_completed else "unknown",
            "error": str(e),
            "error_type": "QualityGateError",
            "gate_name": e.gate_result.gate_name,
            "gate_failures": e.gate_result.failures,
        }
        errors.append(error_data)

        # Write partial validation report even on gate failure
        report = _build_validation_report(book_id, gate_results, artifacts)
        if input.output_dir:
            report_path = Path(input.output_dir) / "validation-report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, default=str))

        if book_id:
            await ctx.db.update_book_status(book_id, BookStatus.FAILED)
            await ctx.state.release_lock(str(book_id))
            pipeline_errors.add(
                1,
                {
                    "stage": error_data["stage"],
                    "error_type": "QualityGateError",
                    "book_id": str(book_id),
                },
            )

        final_status = BookStatus.FAILED
        raise

    except Exception as e:
        logger.exception(f"Pipeline failed: {e}")

        # Record error
        error_data = {
            "stage": stages_completed[-1] if stages_completed else "unknown",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        errors.append(error_data)

        # Write partial validation report
        report = _build_validation_report(book_id, gate_results, artifacts)
        if input.output_dir:
            report_path = Path(input.output_dir) / "validation-report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, default=str))

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
        gate_results=[
            {
                "name": g.gate_name,
                "passed": g.passed,
                "failures": g.failures,
                "details": g.details,
                "timestamp": g.timestamp,
            }
            for g in gate_results
        ],
    )

