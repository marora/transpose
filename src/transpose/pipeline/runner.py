"""Pipeline orchestrator — runs stages in sequence for a book.

Quality gates run between stages and block progression on failure.
A validation report is written to the output directory after export.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from transpose.models.enums import BookStatus, SourceLanguage
from transpose.observability import cost_events
from transpose.pipeline.gates import (
    GateResult,
    QualityGateError,
    artifact_availability_gate,
    document_structure_gate,
    export_rendering_gate,
    glossary_integrity_gate,
    golden_targeted_qa_gate,
    ocr_sanity_gate,
    operational_readiness_gate,
    source_output_comparison_gate,
    translation_completeness_gate,
    validate_production_readiness,
)

logger = logging.getLogger(__name__)

# Type alias: book IDs are always strings at pipeline boundaries.
BookId = str


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
    concurrency: int | None = None
    force_retranslate: bool = False
    # Provenance fields — used to populate metadata.json at the workspace stage.
    source_url: str | None = None       # Download URL of the source scan
    source_edition: str | None = None   # Publisher / edition / year string
    translator_note: str | None = None  # Optional per-book OG description


@dataclass
class PipelineOutput:
    """Top-level output of the full pipeline."""

    book_id: BookId
    status: BookStatus
    artifacts: list[dict]
    glossary_term_count: int
    total_tokens_used: int
    stages_completed: list[str]
    errors: list[dict]
    gate_results: list[dict] = field(default_factory=list)
    cost_summary: dict | None = None
    landing_page_url: str | None = None  # Set after workspace stage completes


STAGE_ORDER = ["ingest", "ocr", "chunk", "translate", "glossary", "assemble", "export", "workspace"]


def _run_gate(gate_fn, gate_input, gate_results: list[GateResult]) -> GateResult:
    """Execute a quality gate, log the result, and raise on failure.

    Emits an OpenTelemetry span and records gate metrics (execution count
    and duration) so dashboards and traces capture gate behaviour.
    """
    import time

    from opentelemetry import trace

    from transpose.observability.metrics import gate_duration_seconds, gate_executions

    tracer = trace.get_tracer("transpose")

    # Run the gate inside a span so it shows up in distributed traces
    start = time.monotonic()
    with tracer.start_as_current_span("quality_gate") as span:
        result = gate_fn(gate_input)
        duration = time.monotonic() - start
        # Stamp duration on the result so the validation report can surface it.
        result.duration_ms = round(duration * 1000, 2)

        # Annotate the span with gate metadata
        span.set_attribute("gate.name", result.gate_name)
        span.set_attribute("gate.passed", result.passed)
        span.set_attribute("gate.duration_ms", result.duration_ms)
        if not result.passed:
            span.set_attribute("gate.failure_reason", "; ".join(result.failures))

        # Record metrics for dashboards
        result_label = "pass" if result.passed else "fail"
        gate_executions.add(1, {"gate_name": result.gate_name, "result": result_label})
        gate_duration_seconds.record(duration, {"gate_name": result.gate_name})

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
    book_id: BookId | None,
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
                "duration_ms": g.duration_ms,
            }
            for g in gate_results
        ],
        "overall": overall,
        "artifacts": artifact_map,
    }


async def _persist_validation_report(ctx, book_id, report: dict, oracle_score: dict | None = None) -> None:
    """Best-effort: write the validation report to Postgres for the dashboard.

    Never raises — observability must not block the pipeline. Called from
    every terminal branch in run_pipeline (success + both error paths).

    Args:
        ctx: Service context.
        book_id: Book UUID.
        report: Validation report payload.
        oracle_score: Optional Layer C quality score from oracle judge.
    """
    if not book_id or not ctx or not getattr(ctx, "db", None):
        return
    try:
        import uuid as _uuid
        bid = book_id if isinstance(book_id, _uuid.UUID) else _uuid.UUID(str(book_id))
        await ctx.db.ensure_validation_reports_table()
        await ctx.db.save_validation_report(bid, report, oracle_score)
    except Exception as exc:
        logger.warning("Failed to persist validation report: %s", exc)



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

    from . import (
        assemble,
        chunk,
        export,
        glossary,
        ingest,
        ocr,
        translate,
    )
    from . import (
        workspace as workspace_mod,
    )

    logger = logging.getLogger(__name__)

    # Initialize service context if not provided
    if ctx is None:
        ctx = ServiceContext()
        await ctx.connect()

    # Cost tracking (initialized once we have a book_id)
    from transpose.observability.cost_tracker import CostTracker

    cost_tracker: CostTracker | None = None

    pipeline_start_time = datetime.now()

    # Append-only stage-level cost telemetry (#97). One run_id per invocation
    # so resumes show up as fresh rows in book_cost_events.
    run_id = uuid4()
    _active_event: dict[str, Any] = {
        "id": None,
        "stage": None,
        "before": cost_events.snapshot_tracker(None),
    }

    async def _begin_stage_event(stage: str, start: datetime) -> None:
        """Record stage-start event. Safe to call before book_id is known."""
        if not book_id:
            return
        _active_event["before"] = cost_events.snapshot_tracker(cost_tracker)
        _active_event["id"] = await cost_events.record_stage_start(
            ctx.db,
            book_id=book_id,
            run_id=run_id,
            stage_name=stage,
            started_at=start,
        )
        _active_event["stage"] = stage

    async def _end_stage_event(
        status: str = "completed", error: str | None = None
    ) -> None:
        """Finalize the in-flight stage event with metrics delta."""
        eid = _active_event["id"]
        if eid is None:
            return
        after = cost_events.snapshot_tracker(cost_tracker)
        metrics = cost_events.delta(_active_event["before"], after)
        await cost_events.record_stage_end(
            ctx.db, eid, status=status, metrics=metrics, error_message=error
        )
        _active_event["id"] = None
        _active_event["stage"] = None

    stages_completed: list[str] = []
    errors: list[dict] = []
    gate_results: list[GateResult] = []
    book_id = None
    artifacts: list[dict] = []
    glossary_term_count = 0
    total_tokens = 0
    landing_page_url: str | None = None
    # Track outputs needed by the workspace stage
    _ingest_output = None
    _export_output = None

    # Determine which stages to run
    start_index = 0
    if input.resume_from:
        try:
            start_index = STAGE_ORDER.index(input.resume_from)
            logger.info(f"Resuming from stage: {input.resume_from}")
        except ValueError:
            logger.warning(f"Unknown stage: {input.resume_from}, starting from beginning")

    # When resuming past ingest, look up the existing book_id from the source PDF hash
    source_or_blob = input.source_path or input.blob_uri
    if start_index > STAGE_ORDER.index("ingest") and source_or_blob:
        import hashlib

        existing = None
        pdf_path = Path(input.source_path) if input.source_path else None
        if pdf_path and pdf_path.exists():
            source_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            existing = await ctx.db.get_book_by_hash(source_hash)
        else:
            # Source is a URL/blob — try to extract hash from blob name
            lookup_url = input.blob_uri or input.source_path
            blob_name = str(lookup_url).rsplit("/", 1)[-1].removesuffix(".pdf")
            if len(blob_name) == 64:
                existing = await ctx.db.get_book_by_hash(blob_name)
            if not existing:
                # Fall back: look up the most recent book by title
                row = await ctx.db.fetch_one(
                    "SELECT id FROM books WHERE title = $1 ORDER BY created_at DESC LIMIT 1",
                    input.title,
                )
                if row:
                    from types import SimpleNamespace
                    existing = SimpleNamespace(id=row["id"])

        if existing:
            book_id = str(existing.id)
            cost_tracker = CostTracker(book_id)
            logger.info(f"Resumed with book_id={book_id}")
        else:
            raise ValueError(
                "Cannot resume: no book found for the given source. "
                "Run from the beginning first."
            )

    # --- Operational Readiness Preflight (Gate 8) ---
    # Non-blocking by default — logs failures as warnings.
    # Set TRANSPOSE_PREFLIGHT_BLOCK=1 to make failures halt the pipeline.
    import os

    preflight_blocking = os.environ.get("TRANSPOSE_PREFLIGHT_BLOCK", "") == "1"
    logger.info("=== Preflight: Operational Readiness ===")
    try:
        preflight = await operational_readiness_gate(ctx)
        if not preflight.passed:
            msg = f"Operational readiness: {'; '.join(preflight.failures)}"
            if preflight_blocking:
                logger.error("❌ %s", msg)
                raise RuntimeError(msg)
            else:
                logger.warning("⚠️  %s (non-blocking)", msg)
        else:
            logger.info(
                "✅ Operational readiness preflight PASSED (%d checks)",
                len(preflight.checks),
            )
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning("⚠️  Preflight check error (non-blocking): %s", exc)

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

            book_id = str(ingest_output.book_id)
            _ingest_output = ingest_output
            cost_tracker = CostTracker(book_id)

            # Track blob upload from ingest (source PDF)
            if not ingest_output.already_existed:
                cost_tracker.record_blob_operation("write")

            # cost_events: ingest started before book_id existed; record now
            await _begin_stage_event("ingest", start_time)

            # Acquire distributed lock before proceeding to expensive stages
            lock_acquired = await ctx.state.acquire_lock(str(book_id))
            if not lock_acquired:
                logger.warning(
                    "Lock already held for book_id=%s — another pipeline run is in progress",
                    book_id,
                )
                await ctx.state.set_pipeline_status(str(book_id), "locked")
                return PipelineOutput(
                    book_id=book_id,
                    status=BookStatus.PROCESSING,
                    artifacts=[],
                    glossary_term_count=0,
                    total_tokens_used=0,
                    stages_completed=stages_completed,
                    errors=[{
                        "stage": "ingest",
                        "error": "Pipeline already in progress for this book",
                        "error_type": "LockConflict",
                    }],
                )

            await ctx.state.set_pipeline_status(str(book_id), "ingest")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "ingest", "book_id": str(book_id)})
            stages_completed.append("ingest")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 7, "ingest", duration, elapsed_total, str(book_id),
            )

            logger.info(
                f"Ingest complete: book_id={book_id}, "
                f"pages={ingest_output.page_count}, "
                f"already_existed={ingest_output.already_existed}"
            )

        # Stage 2: OCR
        if start_index <= STAGE_ORDER.index("ocr"):
            logger.info("=== Stage 2: OCR ===")
            start_time = datetime.now()
            await _begin_stage_event("ocr", start_time)

            # Need book_id from previous stage or resume
            if not book_id and input.resume_from:
                # For resume, we need to get book_id from somewhere
                # This is a simplification - in production, you'd pass book_id explicitly
                raise ValueError("book_id required for resume_from")

            ocr_output = await ocr.run(
                ocr.OcrInput(book_id=book_id, force_reocr=input.force_retranslate),
                ctx,
            )

            # Track OCR cost
            if cost_tracker:
                cost_tracker.record_ocr_pages(ocr_output.pages_processed)

            await ctx.state.set_pipeline_status(str(book_id), "ocr")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "ocr", "book_id": str(book_id)})
            stages_completed.append("ocr")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 7, "ocr", duration, elapsed_total, str(book_id),
            )

            logger.info(
                f"OCR complete: processed={ocr_output.pages_processed}, "
                f"skipped={ocr_output.pages_skipped}, "
                f"low_confidence={ocr_output.low_confidence_count}"
            )

            # Quality Gate: OCR Sanity
            _run_gate(
                lambda out: ocr_sanity_gate(
                    out,
                    min_confidence=ctx.settings.low_confidence_threshold,
                ),
                ocr_output,
                gate_results,
            )

        # Stage 3: Chunk
        if start_index <= STAGE_ORDER.index("chunk"):
            logger.info("=== Stage 3: Chunk ===")
            start_time = datetime.now()
            await _begin_stage_event("chunk", start_time)

            chunk_output = await chunk.run(
                chunk.ChunkInput(
                    book_id=book_id,
                    target_chunk_tokens=ctx.settings.chunk_target_tokens,
                    overlap_tokens=ctx.settings.chunk_overlap_tokens,
                    force_rechunk=input.force_retranslate,
                ),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "chunk")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "chunk", "book_id": str(book_id)})
            stages_completed.append("chunk")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 7, "chunk", duration, elapsed_total, str(book_id),
            )

            logger.info(f"Chunk complete: total_chunks={chunk_output.total_chunks}")

        # Stage 4: Translate
        if start_index <= STAGE_ORDER.index("translate"):
            logger.info("=== Stage 4: Translate ===")
            start_time = datetime.now()
            await _begin_stage_event("translate", start_time)

            translate_output = await translate.run(
                translate.TranslateInput(
                    book_id=book_id,
                    concurrency=input.concurrency or ctx.settings.translate_concurrency,
                    force_retranslate=input.force_retranslate,
                ),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "translate")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "translate", "book_id": str(book_id)})
            stages_completed.append("translate")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 7, "translate", duration, elapsed_total, str(book_id),
            )

            total_tokens = (
                translate_output.total_prompt_tokens + translate_output.total_completion_tokens
            )

            # Track LLM cost
            if cost_tracker:
                cost_tracker.record_llm_usage(
                    translate_output.total_prompt_tokens,
                    translate_output.total_completion_tokens,
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
            await _begin_stage_event("glossary", start_time)

            glossary_output = await glossary.run(
                glossary.GlossaryInput(book_id=book_id),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "glossary")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "glossary", "book_id": str(book_id)})
            stages_completed.append("glossary")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 7, "glossary", duration, elapsed_total, str(book_id),
            )

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
            await _begin_stage_event("assemble", start_time)

            assemble_output = await assemble.run(
                assemble.AssembleInput(book_id=book_id),
                ctx,
            )

            await ctx.state.set_pipeline_status(str(book_id), "assemble")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "assemble", "book_id": str(book_id)})
            stages_completed.append("assemble")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 7, "assemble", duration, elapsed_total, str(book_id),
            )

            logger.info(f"Assemble complete: chapters={len(assemble_output.chapters)}")

            # Quality Gate: Document Structure
            # Build a lightweight manuscript-like object from assemble_output
            _run_gate(document_structure_gate, assemble_output, gate_results)

        # Stage 7: Export
        if start_index <= STAGE_ORDER.index("export"):
            logger.info("=== Stage 7: Export ===")
            start_time = datetime.now()
            await _begin_stage_event("export", start_time)

            export_output = await export.run(
                export.ExportInput(book_id=book_id, formats=input.output_formats),
                ctx,
            )
            _export_output = export_output

            await ctx.state.set_pipeline_status(str(book_id), "export")

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "export", "book_id": str(book_id)})
            stages_completed.append("export")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 7, "export", duration, elapsed_total, str(book_id),
            )

            artifacts = [
                {
                    "format": artifact.format,
                    "blob_uri": artifact.blob_uri,
                    "file_size_bytes": artifact.file_size_bytes,
                }
                for artifact in export_output.artifacts
            ]

            # Track blob write operations (one per exported artifact)
            if cost_tracker:
                for _artifact in export_output.artifacts:
                    cost_tracker.record_blob_operation("write")

            logger.info(f"Export complete: artifacts={len(artifacts)}")

            # Quality Gate: Artifact Availability
            _run_gate(artifact_availability_gate, export_output, gate_results)

            # Quality Gate: Export Rendering Quality
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
                    lambda _inp: export_rendering_gate(pdf_artifact_path),
                    None,
                    gate_results,
                )

                # Quality Gate: Golden-Targeted QA (runs after all other gates)
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

                # Quality Gate: Source-Output Structural Comparison
                source_pdf = (
                    input.source_path
                    if input.source_path and Path(input.source_path).exists()
                    else None
                )
                _run_gate(
                    lambda _inp: source_output_comparison_gate(source_pdf, pdf_artifact_path),
                    None,
                    gate_results,
                )

        # Stage 8: Workspace — upload artifacts, write metadata.json, publish landing page
        # Runs after export. Non-fatal if static website URL is not configured
        # (will warn and skip rather than blocking the pipeline).
        if start_index <= STAGE_ORDER.index("workspace"):
            logger.info("=== Stage 8: Workspace ===")
            start_time = datetime.now()
            await _begin_stage_event("workspace", start_time)

            static_website_url = ctx.settings.blob_static_website_url
            if not static_website_url:
                logger.warning(
                    "⚠️  TRANSPOSE_BLOB_STATIC_WEBSITE_URL is not set — "
                    "workspace artifacts will still be written, but no public static-site URL "
                    "will be generated. Run Tank's T-1 storage setup and backfill later to publish."
                )
            try:
                landing_page_url = await _run_workspace_stage(
                    book_id=book_id,
                    input=input,
                    ctx=ctx,
                    workspace_mod=workspace_mod,
                    ingest_output=_ingest_output,
                    export_output=_export_output,
                    static_website_url=static_website_url,
                    logger=logger,
                )
                logger.info("🔗 Landing page: %s", landing_page_url)
                print(f"\n🔗  Share URL: {landing_page_url}\n")
            except Exception as exc:
                logger.error(
                    "Workspace stage failed (non-fatal — pipeline artifacts are intact): %s",
                    exc,
                    exc_info=True,
                )
                errors.append({
                    "stage": "workspace",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                })

            duration = (datetime.now() - start_time).total_seconds()
            stage_duration.record(duration, {"stage": "workspace", "book_id": str(book_id)})
            stages_completed.append("workspace")
            await _end_stage_event()
            elapsed_total = (datetime.now() - pipeline_start_time).total_seconds()
            logger.info(
                "📊 Progress: [%d/%d] %s completed in %.1fs (total: %.1fs) | book_id=%s",
                len(stages_completed), 8, "workspace", duration, elapsed_total, str(book_id),
            )

        # Oracle Layer C — post-export quality assessment (non-blocking)
        oracle_score_payload = None
        if book_id and ctx.settings.anthropic_api_key:
            try:
                from transpose.observability.oracle_judge import judge_translation_quality

                logger.info("=== Oracle Layer C: Translation Quality Assessment ===")
                chunks = await ctx.db.get_chunks_for_book(book_id)
                translations = await ctx.db.get_translations_for_book(book_id)

                oracle_score = await judge_translation_quality(
                    book_id=book_id,
                    chunks=chunks,
                    translations=translations,
                    anthropic_api_key=ctx.settings.anthropic_api_key,
                )

                if oracle_score:
                    oracle_score_payload = {
                        "composite_score": oracle_score.composite_score,
                        "fluency": oracle_score.fluency,
                        "cultural_register": oracle_score.cultural_register,
                        "terminology_nuance": oracle_score.terminology_nuance,
                        "sampled_chunk_ids": oracle_score.sampled_chunk_ids,
                        "raw_judge_response": oracle_score.raw_judge_response,
                    }
                    logger.info(
                        "✅ Oracle Layer C: composite_score=%d, fluency=%d, "
                        "cultural_register=%d, terminology_nuance=%d (sampled %d chunks)",
                        oracle_score.composite_score,
                        oracle_score.fluency,
                        oracle_score.cultural_register,
                        oracle_score.terminology_nuance,
                        len(oracle_score.sampled_chunk_ids),
                    )
                else:
                    logger.warning("Oracle Layer C returned no score (check logs for details)")
            except Exception as exc:
                logger.error(
                    "Oracle Layer C failed (non-blocking): %s",
                    exc,
                    exc_info=True,
                )

        # Write validation report
        report = _build_validation_report(book_id, gate_results, artifacts)
        if input.output_dir:
            report_path = Path(input.output_dir) / "validation-report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, default=str))
            logger.info("Validation report written to %s", report_path)
        await _persist_validation_report(ctx, book_id, report, oracle_score_payload)

        # Persist cost tracking
        if cost_tracker:
            try:
                await ctx.db.ensure_book_costs_table()
                await cost_tracker.persist(ctx.db)
            except Exception as exc:
                logger.warning("Failed to persist cost data: %s", exc)

        # Release lock
        if book_id:
            await ctx.state.release_lock(str(book_id))

        final_status = BookStatus.EXPORTED

    except QualityGateError as e:
        logger.error("Pipeline halted by quality gate: %s", e)
        await _end_stage_event(status="failed", error=str(e))

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
        # No oracle_score on gate failures (never reached post-export)
        await _persist_validation_report(ctx, book_id, report, None)

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
        await _end_stage_event(status="failed", error=str(e))

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
        # No oracle_score on generic errors (pipeline may not have reached export)
        await _persist_validation_report(ctx, book_id, report, None)

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

    # Log pipeline timing summary
    pipeline_elapsed = (datetime.now() - pipeline_start_time).total_seconds()
    logger.info(
        "🏁 Pipeline complete in %.1fs (%d stages) | book_id=%s",
        pipeline_elapsed, len(stages_completed), str(book_id),
    )
    stage_duration.record(pipeline_elapsed, {"stage": "total", "book_id": str(book_id)})

    # Build cost summary dict
    cost_summary_dict = None
    if cost_tracker:
        s = cost_tracker.summary()
        cost_summary_dict = {
            "openai": {
                "input_tokens": s.openai_input_tokens,
                "output_tokens": s.openai_output_tokens,
                "cost_usd": round(s.openai_cost_usd, 6),
            },
            "doc_intelligence": {
                "pages": s.ocr_pages,
                "cost_usd": round(s.ocr_cost_usd, 6),
            },
            "blob_storage": {
                "read_ops": s.blob_read_ops,
                "write_ops": s.blob_write_ops,
                "cost_usd": round(s.blob_cost_usd, 6),
            },
            "total_cost_usd": round(s.total_cost_usd, 6),
        }

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
        cost_summary=cost_summary_dict,
        landing_page_url=landing_page_url,
    )


# ──────────────────────────────────────────────
# Workspace stage helper (TR-4)
# ──────────────────────────────────────────────


async def _run_workspace_stage(
    *,
    book_id: str | None,
    input: PipelineInput,
    ctx,
    workspace_mod,
    ingest_output,
    export_output,
    static_website_url: str,
    logger,
) -> str:
    """Execute the workspace publish step after export.

    Steps:
      1.  Resolve book metadata from DB.
      2.  Create BookWorkspace instance.
      3.  Upload source PDF to workspace (copy from existing blob).
      4.  Upload translated PDF to workspace (copy from export artifact blob).
      5.  Build and write metadata.json (license.status = 'rights-unknown' always).
      6.  Generate per-file SAS URLs for source + translated PDFs (30-day, read-only).
      7.  Generate landing page HTML.
      8.  Publish landing page to $web and workspace private copy.
      9.  Update metadata.json with share.* fields and landing_page_url.

    Hard guards enforced here (Layer 3 + "do not auto-claim PD"):
      - metadata.json is created with license.status = 'rights-unknown' only.
      - update_metadata() raises if any caller passes a 'license' key.
      - No pipeline code path upgrades license.status — ever.

    Returns the public landing page URL.
    """
    from transpose.pipeline.workspace import (
        BookWorkspace,
        build_metadata,
        generate_landing_html,
        make_slug,
        validate_metadata,
    )
    from transpose.services.blob_client import BlobClient

    if not book_id:
        raise ValueError("workspace stage requires book_id")

    # Fetch book from DB for title, author, source_language, page_count
    book = await ctx.db.get_book(book_id)
    if not book:
        raise ValueError(f"Book not found in DB: {book_id}")

    slug = make_slug(book.title)

    workspace_blob = BlobClient(
        ctx.settings.blob_storage_account_url,
        allow_local_fallback=False,
        on_rbac_retry=logger.warning,
    )
    ws = BookWorkspace(
        book_id=book_id,
        slug=slug,
        blob_client=workspace_blob,
        static_website_url=static_website_url,
    )

    logger.info(
        "Workspace prefix: %s  landing URL: %s", ws.blob_prefix, ws.landing_page_url
    )

    async def _read_artifact_bytes(uri: str) -> bytes:
        import urllib.parse

        if uri.startswith("file://"):
            parsed = urllib.parse.urlparse(uri)
            return Path(urllib.parse.unquote(parsed.path)).read_bytes()

        from transpose.pipeline.ingest import _parse_blob_uri

        container_name, blob_name = _parse_blob_uri(uri)
        return await ctx.blob.download_blob(container=container_name, blob_name=blob_name)

    try:
        # ── Upload source PDF ──────────────────────────────────────────────────
        source_blob_uri = (
            ingest_output.source_blob_uri
            if ingest_output
            else getattr(book, "source_blob_uri", None)
        )
        if source_blob_uri:
            logger.info("Copying source PDF to workspace: %s", ws.source_blob_name)
            try:
                source_pdf_data = await _read_artifact_bytes(source_blob_uri)
                await ws.upload_source(source_pdf_data)
            except Exception as exc:
                logger.warning(
                    "Could not copy source PDF to workspace (non-fatal): %s", exc
                )
        else:
            logger.warning("No source_blob_uri available — source PDF not copied to workspace")

        # ── Upload translated PDF ──────────────────────────────────────────────
        translated_pdf_blob_uri: str | None = None
        if export_output:
            for artifact in export_output.artifacts:
                if getattr(artifact, "format", "") == "pdf":
                    translated_pdf_blob_uri = getattr(artifact, "blob_uri", None)
                    break

        if translated_pdf_blob_uri:
            logger.info("Copying translated PDF to workspace: %s", ws.translated_blob_name)
            try:
                translated_pdf_data = await _read_artifact_bytes(translated_pdf_blob_uri)
                await ws.upload_translated(translated_pdf_data)
            except Exception as exc:
                logger.warning(
                    "Could not copy translated PDF to workspace (non-fatal): %s", exc
                )
        else:
            logger.warning(
                "No translated PDF artifact available — translated PDF not copied to workspace"
            )

        # ── Build and write initial metadata.json ─────────────────────────────
        # Translator note: from PipelineInput, then env, then synthesized default.
        source_language_str = str(book.source_language).title()  # e.g. "Hindi"

        meta = build_metadata(
            book_id=book_id,
            slug=slug,
            title=book.title,
            author=book.author or "",
            source_language=source_language_str,
            target_language="English",
            page_count=book.page_count or 0,
            source_url=input.source_url,
            source_edition=input.source_edition,
            translator_note=input.translator_note
            or ctx.settings.workspace_translator_note
            or None,
        )

        validation_errors = validate_metadata(meta)
        if validation_errors:
            logger.warning("metadata.json validation warnings: %s", validation_errors)

        # HARD GUARD — Layer 3: this will raise RightsUnknownViolation if violated.
        # Do not catch this exception — let it propagate to signal a code bug.
        await ws.write_metadata(meta)
        logger.info("metadata.json written (license.status=rights-unknown)")

        # ── Generate SAS URLs (30-day read-only per-file) ───────────────────────
        now_utc = datetime.now(UTC)
        sas_expiry = (now_utc + timedelta(days=30)).isoformat()

        try:
            source_sas = await ws.generate_sas_url(ws.source_blob_name, expiry_days=30)
        except Exception as exc:
            logger.warning("SAS URL generation failed for source PDF: %s", exc)
            source_sas = ""

        try:
            translated_sas = await ws.generate_sas_url(
                ws.translated_blob_name, expiry_days=30
            )
        except Exception as exc:
            logger.warning("SAS URL generation failed for translated PDF: %s", exc)
            translated_sas = ""

        # ── Generate landing page HTML ─────────────────────────────────────────
        # Populate share.* before rendering so OG links resolve correctly.
        meta["landing_page_url"] = ws.landing_page_url
        meta["share"]["source_pdf_sas_url"] = source_sas
        meta["share"]["translated_pdf_sas_url"] = translated_sas
        meta["share"]["sas_expiry"] = sas_expiry
        meta["share"]["generated_at"] = now_utc.isoformat()

        html_str = generate_landing_html(meta)

        # ── Publish landing page ───────────────────────────────────────────────
        public_url = await ws.publish_landing_page(html_str)
        logger.info("Landing page published: %s", public_url)

        # ── Update metadata.json with share.* and landing_page_url ────────────
        # GUARD: update_metadata() will raise PipelineLicenseUpgradeGuard if
        # 'license' is in the updates dict — enforcing "do not auto-claim PD".
        share_updates = {
            "landing_page_url": ws.landing_page_url,
            "share": {
                "source_pdf_sas_url": source_sas,
                "translated_pdf_sas_url": translated_sas,
                "sas_expiry": sas_expiry,
                "generated_at": now_utc.isoformat(),
            },
        }
        await ws.update_metadata(share_updates)
        logger.info("metadata.json updated with share URLs")

        return public_url
    finally:
        await workspace_blob.close()

