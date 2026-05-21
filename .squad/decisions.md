# Transpose Decisions Log

Decisions recorded for team memory and cross-agent context.

---

## 2026-05-21T01:22:57-04:00: User directive — Silent fix prohibition

**By:** Manish (via Copilot)

**Decision:** When the team runs into bugs or issues during pipeline execution, ALWAYS open a GitHub issue describing the problem before fixing it. Don't silent-fix.

**Rationale:** User request — captured for team memory. Creates a paper trail and surfaces patterns over time.

---

## 2026-05-21T11:00:50-04:00: User directive — Pipeline hardening priority

**By:** Manish (via Copilot)

**Decision:** Pipeline hardening is the primary goal, not shipping a single book. Manish will feed 3-5 books in coming sessions; pipeline must work end-to-end reliably. Pivot from one-off heroics to systematic robustness.

**Rationale:** Captured for team memory. Drives prioritization: every fix should pay off across multiple books, not just one.

---

## 2026-05-21T11:40:56-04:00: Glossary U+FFFD Scrub Strategy (Issue #89)

**Author:** Trinity

**Status:** Implemented

**Related issue:** #89

### Problem

The glossary stage wrote at least one `GlossaryEntry.original_script` containing U+FFFD (the Unicode replacement character), causing the `glossary_integrity` gate to fail on the Shiv Sutra full-book run. The entry in question was `'shri'` — an LLM-detected term whose `original_script` was sourced from OCR output with a garbled glyph.

`_clean_original_script` was already stripping U+FFFD at three points, but the value could survive if the `_deduplicate_spelling_variants` step merged a variant's `original_script` into the canonical entry after those passes.

### Decision

**Strategy: defensive final scrub at entry-write time**

Rather than auditing every aggregation path to guarantee FFFD can't appear, a **defensive final pass** of `_clean_original_script()` is applied immediately before each `GlossaryEntry` is constructed. This is belt-and-suspenders: all existing scrubs remain, plus a guaranteed last checkpoint.

**Strip vs. Reject:**
- **Strip preferred** when valid Devanagari codepoints survive after stripping FFFD
- **Reject (empty string)** when remainder after FFFD removal is Latin-only or empty

### Module-level extraction

`_clean_original_script` was promoted from nested function inside `run()` to module-level so it can be unit-tested directly and reused without coupling to `run()`.

### Tests added

`tests/unit/pipeline/test_glossary.py :: TestCleanOriginalScriptUFFfd` (5 tests):
- `test_scrub_path_recoverable_string`
- `test_reject_path_all_fffd`
- `test_clean_script_no_fffd_passthrough`
- `test_leading_trailing_fffd_stripped`
- `test_mixed_fffd_and_latin_returns_empty`

All 353 unit tests pass.

---

## 2026-05-21T11:40:56-04:00: export_rendering Repeated-Image Heuristic (Issue #90)

**Author:** Trinity

**Status:** Implemented

**Related issue:** #90

### Problem

The `export_rendering` gate was failing on the Shiv Sutra export with a flag for any single large image (≥25% of page area) appearing on 3+ pages. Real books routinely contain cover art, chapter ornaments, and publisher logos that legitimately repeat.

### Decision

**New threshold: ≥ 2 distinct large images each repeating 3+ times**

Changed `if significant_dupes:` to `if significant_dupes >= 2:`.

A **single repeated image** (even if large, even if on many pages) is **never flagged**. Only when **two or more distinct large images** each appear 3+ times does the gate fail — this pattern indicates an assembly pipeline bug.

### Tests updated

`tests/unit/pipeline/test_gates.py :: TestExportRenderingGate`:
- `test_fails_on_large_repeated_placed_images` — updated to use 2 distinct images both repeating
- `test_passes_single_large_repeated_image_real_book` — new test: ONE large image repeating 5 pages; gate must pass

All 353 unit tests pass.

---

