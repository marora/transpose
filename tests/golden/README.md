# Golden Reference Data

This directory contains the **golden reference** for regression testing the
Transpose pipeline output against the 10-page Hindi test PDF
(`tests/fixtures/test-hindi-10page.pdf`).

## Files

| File | Purpose |
|---|---|
| `expected-structure.json` | Document structure: chapter count, titles, front/back matter |
| `expected-glossary.json` | Golden glossary entries with Devanagari + English definitions |
| `gate-expectations.json` | Expected quality-gate pass/fail results |

## How regression tests work

Tests in `tests/regression/test_golden_reference.py` compare pipeline output
against these files.  They are marked `@pytest.mark.regression` and
`@pytest.mark.slow` because they require a full (or cached) pipeline run.

Quick summary of what is checked:

1. **Structure** — chapter count, title fragments, presence of foreword / ToC / glossary.
2. **Glossary** — preserved terms present, Devanagari exact-match (NFC-normalised),
   definition keywords.
3. **Gates** — every quality gate must pass.
4. **No source leak** — no full Devanagari sentences survive in the English output.
5. **Artifact sizes** — PDF and ePub within sane bounds.
6. **Page count** — output pages ≤ 1.5× source pages.

## How to update the golden reference

1. Run a full pipeline on the test PDF and **manually review** the output.
2. If the output is correct, regenerate the golden files:
   ```bash
   python scripts/update_golden_reference.py   # (future — not yet implemented)
   ```
   Or edit the JSON files by hand.
3. Commit the updated golden files with a clear message explaining *why*.

> **Rule:** golden data is updated intentionally, never automatically.
> A failing regression test means "investigate", not "overwrite".
