# Decision: Gate 7 — Production Readiness Visual Inspection Proxy

**Author:** Chani (Pipeline Developer)
**Date:** 2026-04-20
**Status:** Implemented
**Issue:** #15

## Context

Stilgar's Round 2 visual inspection found 4 rendering/data defects in PDF output: Devanagari garbling, ToC page numbers all showing "1", halant misordering, and sangat showing wrong script (Devanagari instead of Gurmukhi). These defects were only caught by manual visual review — no automated gate existed to catch them.

## Decision

Add Gate 7 (`validate_production_readiness`) as a permanent post-export QA gate that acts as an automated proxy for visual inspection. It runs 6 checks against the rendered PDF:

1. **devanagari_integrity** — IPA Extension chars and digit-in-Devanagari substitutions in glossary (with tolerance for PyMuPDF extraction artifacts)
2. **toc_verification** — ToC page numbers present and not all identical
3. **content_completeness** — word count within 0.7×–2.0× of golden target
4. **script_hygiene** — body text ≤2% Devanagari (English translation)
5. **cover_validation** — title page exists and has content
6. **structural_integrity** — no empty pages, minimum page count

## Key Design Choices

### Tolerant Devanagari Thresholds

PyMuPDF text extraction garbles Devanagari conjunct glyphs (e.g. धर्म → ध2र्म). This is a known text-extraction limitation, not a rendering defect (confirmed by pixmap rendering). Gate 7 therefore uses tolerances (IPA ≤15, digit-in-Devanagari ≤8) rather than zero-tolerance for these metrics.

### Two-Pass ToC Rendering

WeasyPrint's `target-counter()` CSS function is unreliable. We use a two-pass approach: Pass 1 renders with placeholders, PyMuPDF extracts actual page numbers, Pass 2 renders with hard-coded numbers.

### Seed Glossary Override at Export Time

LLM-detected `original_script` values in the DB are sometimes hallucinated (e.g. wrong script for Sikh terms). At export time, seed glossary values override DB values to ensure curated terms always render correctly.

## Consequences

- All 4 defect classes from Round 2 are now caught automatically
- Gate 7 runs after export in the pipeline runner (after golden targeted QA gate)
- PyMuPDF text extraction artifacts are documented and tolerated — future threshold adjustments may be needed as font rendering evolves
- 473 tests pass, 5 xfailed (pre-existing), 0 failures
