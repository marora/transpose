"""E2E validation run — reconstruct stage outputs from cached DB data and run all quality gates.

Uses book_id d6671336-522a-48b6-82ee-624380d706b8 from the previous pipeline run.
Runs gates on reconstructed outputs, then runs export stage for fresh artifacts.
Writes validation-report.json to repo root.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

# TLS workaround for Azure PostgreSQL on WSL2
os.environ.setdefault("PGSSLCRL", "")
os.environ.setdefault("PGSSLCRLDIR", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("e2e_validation")

BOOK_ID = UUID("d6671336-522a-48b6-82ee-624380d706b8")
REPO_ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    from transpose.pipeline.gates import (
        GateResult,
        artifact_availability_gate,
        document_structure_gate,
        glossary_integrity_gate,
        ocr_sanity_gate,
        translation_completeness_gate,
    )
    from transpose.services import ServiceContext

    ctx = ServiceContext()
    await ctx.connect()

    gate_results: list[GateResult] = []
    artifacts: list[dict] = []
    errors: list[dict] = []

    try:
        # ----------------------------------------------------------------
        # Reconstruct stage outputs from cached DB data
        # ----------------------------------------------------------------

        # --- OCR output reconstruction ---
        logger.info("=== Reconstructing OCR output from DB ===")
        pages = await ctx.db.get_pages_for_book(BOOK_ID)
        logger.info(f"  Pages loaded: {len(pages)}")

        @dataclass
        class PageResult:
            page_number: int
            raw_text: str
            confidence: float | None

        @dataclass
        class OcrOutputProxy:
            page_results: list[PageResult]
            pages_processed: int
            pages_skipped: int
            low_confidence_count: int

        page_results = [
            PageResult(
                page_number=p.page_number,
                raw_text=p.raw_text or "",
                confidence=p.confidence,
            )
            for p in pages
        ]
        ocr_output = OcrOutputProxy(
            page_results=page_results,
            pages_processed=len(pages),
            pages_skipped=0,
            low_confidence_count=sum(1 for p in pages if (p.confidence or 1.0) < 0.6),
        )

        # --- Run OCR Sanity Gate ---
        logger.info("=== Gate 1: OCR Sanity ===")
        try:
            result = ocr_sanity_gate(ocr_output)
            gate_results.append(result)
            if result.passed:
                logger.info("  ✅ OCR Sanity PASSED")
            else:
                logger.warning(f"  ❌ OCR Sanity FAILED: {'; '.join(result.failures)}")
        except Exception as e:
            logger.error(f"  ❌ OCR Sanity gate error: {e}")
            gate_results.append(GateResult(
                gate_name="ocr_sanity", passed=False,
                failures=[f"Gate execution error: {e}"],
            ))

        # --- Translation output reconstruction ---
        logger.info("=== Reconstructing Translation output from DB ===")
        translations = await ctx.db.get_translations_for_book(BOOK_ID)
        chunks = await ctx.db.get_chunks_for_book(BOOK_ID)
        logger.info(f"  Translations loaded: {len(translations)}, Chunks: {len(chunks)}")

        @dataclass
        class TranslationProxy:
            chunk_id: UUID
            translated_text: str

        @dataclass
        class TranslateOutputProxy:
            translations: list[TranslationProxy]
            chunks_translated: int
            failed_count: int

        translation_proxies = [
            TranslationProxy(
                chunk_id=t.chunk_id,
                translated_text=t.translated_text or "",
            )
            for t in translations
        ]
        failed_count = sum(
            1 for t in translations
            if "[TRANSLATION FAILED" in (t.translated_text or "")
        )
        translate_output = TranslateOutputProxy(
            translations=translation_proxies,
            chunks_translated=len(translations),
            failed_count=failed_count,
        )

        # --- Run Translation Completeness Gate ---
        logger.info("=== Gate 2: Translation Completeness ===")
        try:
            result = translation_completeness_gate(translate_output)
            gate_results.append(result)
            if result.passed:
                logger.info("  ✅ Translation Completeness PASSED")
            else:
                logger.warning(f"  ❌ Translation Completeness FAILED: {'; '.join(result.failures)}")
        except Exception as e:
            logger.error(f"  ❌ Translation Completeness gate error: {e}")
            gate_results.append(GateResult(
                gate_name="translation_completeness", passed=False,
                failures=[f"Gate execution error: {e}"],
            ))

        # --- Glossary output reconstruction ---
        logger.info("=== Reconstructing Glossary output from DB ===")
        glossary = await ctx.db.get_glossary_for_book(BOOK_ID)
        terms = await ctx.db.get_cultural_terms_for_book(BOOK_ID)
        logger.info(f"  Glossary: {glossary.id if glossary else 'None'}, Terms: {len(terms)}")

        @dataclass
        class GlossaryEntryProxy:
            term: str
            original_script: str
            definition: str
            source: str
            occurrence_count: int
            needs_review: bool = False

        @dataclass
        class GlossaryOutputProxy:
            entries: list[GlossaryEntryProxy]
            total_terms: int
            needs_review_count: int

        glossary_entries = [
            GlossaryEntryProxy(
                term=t.term,
                original_script=t.original_script or "",
                definition=t.definition or "",
                source=str(t.source),
                occurrence_count=getattr(t, "occurrence_count", 1),
                needs_review=getattr(t, "needs_review", False),
            )
            for t in terms
        ]
        glossary_output = GlossaryOutputProxy(
            entries=glossary_entries,
            total_terms=len(terms),
            needs_review_count=sum(1 for e in glossary_entries if e.needs_review),
        )

        # --- Run Glossary Integrity Gate ---
        logger.info("=== Gate 3: Glossary Integrity ===")
        try:
            result = glossary_integrity_gate(glossary_output)
            gate_results.append(result)
            if result.passed:
                logger.info("  ✅ Glossary Integrity PASSED")
            else:
                logger.warning(f"  ❌ Glossary Integrity FAILED: {'; '.join(result.failures)}")
        except Exception as e:
            logger.error(f"  ❌ Glossary Integrity gate error: {e}")
            gate_results.append(GateResult(
                gate_name="glossary_integrity", passed=False,
                failures=[f"Gate execution error: {e}"],
            ))

        # --- Document Structure Gate (on manuscript) ---
        logger.info("=== Reconstructing Manuscript for Document Structure Gate ===")
        manuscript = await ctx.db.get_manuscript_for_book(BOOK_ID)

        if manuscript:
            logger.info(f"  Manuscript: {manuscript.id}, Title: {manuscript.title}")
            logger.info(f"  Chapters: {len(manuscript.chapters)}, TOC: {len(manuscript.table_of_contents)}")
            foreword = (manuscript.metadata or {}).get("foreword", "")
            logger.info(f"  Foreword: {len(foreword)} chars, {len(foreword.split())} words")

            # The document_structure_gate expects: chapters, table_of_contents, title, metadata
            # The manuscript model has these directly, so we can pass it
            logger.info("=== Gate 4: Document Structure ===")
            try:
                result = document_structure_gate(manuscript)
                gate_results.append(result)
                if result.passed:
                    logger.info("  ✅ Document Structure PASSED")
                else:
                    logger.warning(f"  ❌ Document Structure FAILED: {'; '.join(result.failures)}")
            except Exception as e:
                logger.error(f"  ❌ Document Structure gate error: {e}")
                gate_results.append(GateResult(
                    gate_name="document_structure", passed=False,
                    failures=[f"Gate execution error: {e}"],
                ))
        else:
            logger.error("  No manuscript found — skipping document structure gate")
            gate_results.append(GateResult(
                gate_name="document_structure", passed=False,
                failures=["No manuscript found in database"],
            ))

        # ----------------------------------------------------------------
        # Run Export Stage (local generation, skip blob upload)
        # ----------------------------------------------------------------
        logger.info("=== Stage 7: Export (local generation, no blob upload) ===")
        try:
            from transpose.pipeline.export import (
                ExportArtifact,
                ExportOutput,
                _generate_epub,
                _generate_pdf,
            )

            book = await ctx.db.get_book(BOOK_ID)
            glossary_model = await ctx.db.get_glossary_for_book(BOOK_ID)

            export_artifacts: list[ExportArtifact] = []

            # Generate ePub locally
            logger.info("  Generating ePub...")
            epub_data = await _generate_epub(manuscript, glossary_model, book)
            epub_path = REPO_ROOT / "Test_Hindi_Book_final.epub"
            epub_path.write_bytes(epub_data)
            export_artifacts.append(ExportArtifact(
                format="epub",
                blob_uri=str(epub_path),
                file_size_bytes=len(epub_data),
            ))
            logger.info(f"    ePub: {len(epub_data)} bytes -> {epub_path}")

            # Generate PDF locally
            logger.info("  Generating PDF...")
            pdf_data = await _generate_pdf(manuscript, glossary_model, book)
            pdf_path = REPO_ROOT / "Test_Hindi_Book_final.pdf"
            pdf_path.write_bytes(pdf_data)
            export_artifacts.append(ExportArtifact(
                format="pdf",
                blob_uri=str(pdf_path),
                file_size_bytes=len(pdf_data),
            ))
            logger.info(f"    PDF: {len(pdf_data)} bytes -> {pdf_path}")

            export_output = ExportOutput(
                book_id=BOOK_ID,
                artifacts=export_artifacts,
            )

            artifacts = [
                {
                    "format": a.format,
                    "blob_uri": a.blob_uri,
                    "file_size_bytes": a.file_size_bytes,
                }
                for a in export_artifacts
            ]

            # --- Run Artifact Availability Gate ---
            logger.info("=== Gate 5: Artifact Availability ===")
            try:
                result = artifact_availability_gate(export_output)
                gate_results.append(result)
                if result.passed:
                    logger.info("  ✅ Artifact Availability PASSED")
                else:
                    logger.warning(f"  ❌ Artifact Availability FAILED: {'; '.join(result.failures)}")
            except Exception as e:
                logger.error(f"  ❌ Artifact Availability gate error: {e}")
                gate_results.append(GateResult(
                    gate_name="artifact_availability", passed=False,
                    failures=[f"Gate execution error: {e}"],
                ))

        except Exception as e:
            logger.error(f"  Export stage failed: {e}", exc_info=True)
            errors.append({"stage": "export", "error": str(e), "error_type": type(e).__name__})
            gate_results.append(GateResult(
                gate_name="artifact_availability", passed=False,
                failures=[f"Export stage failed: {e}"],
            ))

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        errors.append({"stage": "validation", "error": str(e), "error_type": type(e).__name__})

    finally:
        # ----------------------------------------------------------------
        # Build and write validation report
        # ----------------------------------------------------------------
        overall = "PASS" if gate_results and all(g.passed for g in gate_results) else "FAIL"

        artifact_map = {}
        for a in artifacts:
            artifact_map[a["format"]] = {
                "path": a.get("blob_uri", ""),
                "size_bytes": a.get("file_size_bytes", 0),
            }

        report = {
            "book_id": str(BOOK_ID),
            "timestamp": datetime.now(UTC).isoformat(),
            "overall": overall,
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
            "artifacts": artifact_map,
            "errors": errors,
            "summary": {
                "total_gates": len(gate_results),
                "passed": sum(1 for g in gate_results if g.passed),
                "failed": sum(1 for g in gate_results if not g.passed),
            },
        }

        report_path = REPO_ROOT / "validation-report.json"
        report_path.write_text(json.dumps(report, indent=2, default=str))
        logger.info(f"\n{'='*60}")
        logger.info(f"VALIDATION REPORT: {overall}")
        logger.info(f"  Gates: {report['summary']['passed']}/{report['summary']['total_gates']} passed")
        for g in gate_results:
            status = "✅ PASS" if g.passed else "❌ FAIL"
            logger.info(f"  {status} — {g.gate_name}")
            if not g.passed:
                for f in g.failures[:3]:
                    logger.info(f"         {f}")
                if len(g.failures) > 3:
                    logger.info(f"         ... and {len(g.failures) - 3} more")
        logger.info(f"Report written to: {report_path}")
        logger.info(f"{'='*60}")

        await ctx.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
