# Decision: Add Production Readiness Gate (Gate 7)

**Author:** Thufir  
**Date:** 2026-04-21  
**Status:** Proposed  

## Context

Manish reported that the translated output PDF doesn't align well enough with the Hindi source for production use. Chapter names are partial (subtitles after em-dashes are missing). The existing 6 gates don't catch this class of issue.

## Analysis

**Current Gate 6 (`golden_targeted_qa_gate`) checks:**
1. Chapter count (by `Chapter N:` pattern) — catches missing chapters but NOT truncated titles
2. Word count per chapter within ±30% — passes because body content is fine, only the heading is truncated
3. Devanagari ratio in body < 2% — passes correctly
4. Glossary required terms present — passes correctly
5. Page count ≤ 1.5× source — passes correctly

**What Gate 6 MISSES:**
- Chapter title completeness (subtitles stripped: "Chapter 1: Dharma and Karma" instead of "Chapter 1: Dharma and Karma — The Message of the Gita")
- ToC accuracy vs body chapter titles
- Garbled text detection (U+FFFD in output, OCR artifacts)
- Paragraph integrity (broken content blocks)
- Glossary consistency (mixed-script detection)

## Finding: 5 Truncated Chapter Titles

The pipeline PDF (`Test_Hindi_Book_final.pdf`) has truncated titles in 5/9 chapters:
- Ch1: Missing "— The Message of the Gita"
- Ch2: Missing "— Physical and Spiritual Discipline"  
- Ch3: Missing "— Sangat, Langar, and Seva"
- Ch5: Missing "— From Kabir to Premchand"
- Ch9: Missing "— The Continuity of Indian Culture"

The golden reference PDF has full titles. The golden-target.json has full titles in `full_title` fields. But Gate 6 never compares against `full_title`.

## Decision

**Add `test_production_readiness.py` as a new regression test file** with 61 tests covering 8 quality dimensions. This is cleaner than extending Gate 6 because:

1. Gate 6 runs in the pipeline (blocking). These checks are regression-oriented and compare against reference PDFs.
2. Gate 6 takes a single candidate PDF. These tests compare pipeline output vs golden reference PDF + JSON.
3. Different cadence: Gate 6 runs every pipeline execution. Production readiness runs in CI/pre-release.

**These tests should block releases** but not block pipeline runs. Recommend adding a `@pytest.mark.production` marker and gating releases on `pytest -m production`.

## Impact

- 5 new test failures correctly identify the chapter title truncation bug
- Chani needs to investigate why the assemble/export stage drops subtitle text after em-dashes
- Once fixed, all 61 tests should pass

## Files

- `tests/regression/test_production_readiness.py` — 61 tests, 8 test classes
