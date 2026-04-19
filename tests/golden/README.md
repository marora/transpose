# Golden Reference Data

This directory contains the **golden reference** for regression testing the
Transpose pipeline output against the 10-page Hindi test PDF
(`tests/fixtures/test-hindi-10page.pdf`).

## Files

| File | Purpose |
|---|---|
| `expected-structure.json` | Document structure: chapter count, titles, front/back matter |
| `expected-glossary.json` | Golden glossary entries with Devanagari + English definitions |
| `gate-expectations.json` | Expected quality-gate pass/fail results (including golden QA gate) |
| `golden-source-fingerprint.json` | Structural fingerprint of the Hindi source PDF (chapters, word counts, key terms) |
| `golden-target.json` | **Golden target** — stable reference English translation with per-chapter word counts, glossary requirements, and quality thresholds |

## Golden-Targeted QA Process

The golden-targeted QA system uses three artifacts:

1. **Golden Source** (Hindi) — `tests/fixtures/test-hindi-10page.pdf`
   - The stable reference input. Never regenerated.
   - Structural fingerprint stored in `golden-source-fingerprint.json`.

2. **Golden Target** (English) — `golden-target.json`
   - A stable reference of the expected correct English output.
   - Created ONCE from the current best translation (`Test_Hindi_Book_final.pdf`).
   - Updated only when the pipeline legitimately improves.

3. **Candidate Output** (Pipeline result)
   - The actual translated PDF produced by Transpose.
   - Compared against the Golden Target at the QA gate.

### What the Golden QA Gate Checks

| Check | Description |
|---|---|
| Structural match | Chapter count, section presence (cover, ToC, foreword, glossary), chapter ordering |
| Content completeness | Per-chapter word count within ±30% of golden target |
| Script hygiene | No Devanagari characters in English body text (glossary preserved terms excepted) |
| Glossary integrity | All required preserved terms present with correct transliteration |
| No regression | Page count within 1.5× of source page count |

## How regression tests work

Tests in `tests/regression/test_golden_reference.py` compare pipeline output
against these files.  They are marked `@pytest.mark.regression` and
`@pytest.mark.slow` because they require a full (or cached) pipeline run.

Tests in `tests/regression/test_golden_targeted_qa.py` validate:
- Golden source fixture existence and validity
- Golden target fixture existence and validity
- Gate passes for a good candidate (real PDF)
- Gate fails for bad candidates (missing chapters, Hindi bleed, missing glossary)
- Tolerance boundaries (word count ±30%, page count at 1.5×)

## How to update the golden reference

1. Run a full pipeline on the test PDF and **manually review** the output.
2. If the output is correct, update the golden files:
   - Edit `golden-target.json` to reflect the new expected output.
   - Update word counts, chapter titles, glossary terms as needed.
3. Commit the updated golden files with a clear message explaining *why*.

> **Rule:** golden data is updated intentionally, never automatically.
> A failing regression test means "investigate", not "overwrite".
