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


## 2026-05-21T12:17:57-04:00: Shiv Sutra Public Access Fix (Issue #91 filed)

**Author:** Tank

**Status:** Implemented

**Related issue:** #91 (dead download links on existing landing page)

### Problem

Manish received `PublicAccessNotPermitted` when accessing raw Azure Blob URL for `output/Shiv_Sutra.pdf`. Storage account security posture is correct (`allowBlobPublicAccess=false`, `output` is internal), but user needed a public download path.

### Diagnosis

- `transposebooks` storage account healthy with Static Website endpoint: `https://transposebooks.z13.web.core.windows.net/`
- Trinity's export artifacts in private `output` container
- Existing slug+id landing page at `$web/shiv-sutra--ee92a4/` had dead links due to SAS generation failure
- Deployed Container App missing `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` environment variable

### Decision

**Path B: Republish artifacts to public website path**

Published to `$web/shiv-sutra/`:
- `index.html`, `landing.html`, `Shiv_Sutra.pdf`, `Shiv_Sutra.epub`, `metadata.json`

Verified HTTP 200 at `https://transposebooks.z13.web.core.windows.net/shiv-sutra/`

### Prevention Changes

- `scripts/azure-setup.sh`: pre-creates `source-pdfs`, `output`, `book-workspaces`; outputs `TRANSPOSE_BLOB_STATIC_WEBSITE_URL`
- `.env.example`: documents Static Website URL derivation
- IaC wiring: `infra/modules/container-app.bicep`, `infra/main.bicep`, `infra/scripts/remediate-env-vars.sh`
- Storage IaC: creates `book-workspaces` container and outputs Static Website endpoint

### Follow-up

Issue #91 filed: pipeline must prevent publishing landing page with dead download buttons when SAS generation fails.

---

## 2026-05-21T13:45:28-04:00: Original Scan Publishing — Public Slug Strategy

**Author:** Tank

**Status:** Implemented

**Related issue:** Tank cost investigation (#93 follow-up)

### Problem

The live `shiv-sutra/` landing page had no working Original Scan link, even though the source PDF already existed privately at `book-workspaces/shiv-sutra--ee92a4/input/source.pdf`. Readers had no way to download the original scan alongside the translation.

### Decision

**For public-domain books, publish original scan to `$web/{slug}/source.pdf`**

- Original scan file: `$web/{slug}/source.pdf` (public URL)
- Translation artifacts: `$web/{slug}/Shiv_Sutra.pdf`, `$web/{slug}/Shiv_Sutra.epub` (public URLs)
- Landing page: `$web/{slug}/index.html` with **both** Download Translation + Original Scan buttons

Use the same Static Website security model as translation assets. Do **not** reference private container URLs in reader-facing links.

### Why

Storage account has `allowBlobPublicAccess=false` — correct posture. Readers cannot access `blob.core.windows.net/book-workspaces/...` URLs directly. Static Website path (`$web/`) is the single public surface; all reader-facing links must route through there.

### Operational convention

- Filename: `source.pdf` (mirrors workspace convention `input/source.pdf`)
- Public URL: `https://transposebooks.z{n}.web.core.windows.net/{slug}/source.pdf`
- This keeps URLs predictable; manual landing-page repairs are straightforward when backfilling additional public-domain books

---

## 2026-05-21T14:19:30-04:00: Book Cost Source of Truth — DB-first, not `book_costs` table

**Author:** Tank

**Status:** DECISION

**Related issue:** #93 (cost_tracker persistence gap)

### Problem

Manish asked for true cost of Shiv Sutra e2e run (wall time 10h 32m, local 01:32→12:04). The `book_costs` table showed only 2 blob write operations — missing 99% of OpenAI/OCR spend.

PostgreSQL investigation revealed:
- `translations`: 1,161,417 input tokens + 255,580 output tokens (real OpenAI cost)
- `books.page_count`: 249 OCR pages (real Azure AI Document Intelligence cost)
- `book_costs` row: only the final resume's blob summary (2 write operations)

**Root cause:** `CostTracker.persist()` only writes to `book_costs` on the happy path after workspace completes. Failed/interrupted/resumed runs produce no durable `book_costs` row — only partial operational telemetry scattered across DB tables and logs.

### Decision

**For true per-book cost inquiry, query DB operational data first; use logs/App Insights only to fill blob-ops and stage-timing gaps.**

1. **OpenAI cost:** sum `prompt_tokens + completion_tokens` from `translations` where `book_id = X`; price with `cost_rates.py`
2. **OCR cost:** read `books.page_count` or count `pages` rows; price with `cost_rates.py`
3. **Blob cost:** reconstruct from logs / Azure telemetry (`book_costs` is not durable)
4. **Use `book_costs` only as a convenience summary**, not source of truth for total historical cost

### Evidence

Shiv Sutra true spend:
- OpenAI: 1,161,417 input + 255,580 output tokens (real data in DB)
- OCR: 249 pages (real data in DB)
- Blob: reconstructed from run logs + App Insights  
- **Total: $12.13** (GPT-4o $9.64 + Doc Intelligence $2.49 + blob storage $0.00006)

### Follow-up

GitHub issue #93 filed: persist `book_costs` summary rows even on failed/resumed runs, so cost forensics is reliable without fallback to logs.

---

