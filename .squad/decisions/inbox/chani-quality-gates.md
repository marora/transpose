# Decision: Blocking Quality Gates in Pipeline

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  

## Summary

Five blocking quality gates inserted between pipeline stages. Each gate validates the output of the preceding stage before allowing the next stage to run. On failure, a `QualityGateError` halts the pipeline and writes a partial validation report.

## Gate Placement

```
Ingest → OCR → [ocr_sanity_gate] → Chunk → Translate → [translation_completeness_gate]
→ Glossary → [glossary_integrity_gate] → Assemble → [document_structure_gate]
→ Export → [artifact_availability_gate] → Done
```

## Key Decisions

1. **Duck-typed inputs** — Gates use `getattr()` instead of importing stage output types. This avoids circular imports and allows testing with simple stub objects.
2. **GateResult dataclass** — Uniform return type with `passed`, `failures` (list of human-readable strings), `details` (dict for structured data), and `timestamp`.
3. **QualityGateError exception** — Wraps a GateResult so the runner can catch, log, and write a partial validation report before aborting.
4. **Validation report** — JSON file written to `{output_dir}/validation-report.json` containing all gate results, pipeline status, and timestamp. Written even on failure (partial).
5. **CI enforcement** — `.github/workflows/quality-gates.yml` runs gate tests on PRs to main and blocks merge on failure.

## Thresholds

| Gate | Key Thresholds |
|------|---------------|
| OCR sanity | <5% replacement chars, >30% Devanagari density, >0.5 avg confidence |
| Translation completeness | <10% failed translations, <5% Devanagari passthrough, no TRANSLATION FAILED markers |
| Glossary integrity | NFC normalization, no replacement chars, no Latin in original_script, ≥1 entry |
| Document structure | ToC matches chapter count, foreword >100 chars, title present, sequential numbering |
| Artifact availability | Both PDF and ePub present, each >1KB, valid URI format |

## Impact

- **Chani:** Gates catch data quality issues before they propagate downstream (e.g., bad OCR won't waste translation API calls)
- **Thufir:** 34 unit tests added; gate interface is stable for regression test expansion
- **Stilgar:** No architecture changes; gates are internal to the runner
- **Idaho:** CI workflow added; no infra changes needed
