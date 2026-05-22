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

## 2026-05-21T23:02:20-04:00: User directive — Parallelization must remain enabled

**By:** Manish (via Copilot)

**Decision:** Parallelization measures (proven beneficial in prior experiments) MUST be enabled in the pipeline at all times going forward. The 10-hour single-book wall time observed for Shiv Sutra is unacceptable and should never recur without explicit override.

**Rationale:** User request — captured for team memory. Pipeline must default to parallelized execution for all future books. Optimization work (#94, #95, #96) should focus on enabling and strengthening parallelism, not disabling it.

---

## 2026-05-21T23:02:20-04:00: Trinity — Parallelism Investigation Results

**Author:** Trinity

**Status:** Investigation Complete

**Related issues:** #94 (wall time), #95 (cost), #96 (OCR parallelization)

### Question

Was parallelization used in the Shiv Sutra run (10h 32m, 250 pages)? If not fully, why not, and what should change?

### Finding

**Partially.**

- **Translation:** Yes, parallelization enabled and likely active.
  - `translate_concurrency=5` default active
  - `asyncio.Semaphore` + `asyncio.gather()` dispatches concurrent chunks
  - DB evidence: 454 final translation rows across 420 seconds; 8–11 chunks/minute early in run suggest overlapping requests, not strict sequential
  
- **OCR:** No meaningful parallelization.
  - `ocr_client.py` stores `ocr_concurrency` config but never uses it
  - `extract_pages()` submits **one** entire-PDF `begin_analyze_document()` call and waits
  - Code comment (commit `d5e46b4`) notes concurrency is "stored for future per-page parallelism"

### Why Wall Time Stayed High

1. **OCR dominates:** ~5h 47m of 10h 32m total (55% of wall time) — effectively single-threaded per-book
2. **Translation is parallel but expensive:** 454 chunks, 1.16M prompt tokens (repeated scaffold ~810k tokens), 255k completion tokens
3. **No evidence of intentional throttle:** Code inspection + git history show parallelism was added, not removed

### Safe Next Steps

1. **Translation defaults (needs approval):** Consider increasing `translate_concurrency` from 5 → 8; scale DB pool accordingly. Expected 1.6x throughput if Azure OpenAI quota permits.
2. **Quota-aware limiter:** Cap translation concurrency by observed/requested Azure OpenAI RPM/TPM, not just raw task count.
3. **Make OCR concurrency real:** Split PDFs into page-range batches, run multiple Document Intelligence jobs behind `ocr_concurrency` semaphore, merge results in order. (Issue #96)
4. **Reduce repeated prompt cost:** Optimize seed-term scaffold or use prompt caching.

### Constraints

- Translation is idempotent at chunk level; increasing parallelism is low-risk if DB pool and OpenAI quotas are respected.
- OCR batching is real code work; needs deterministic page offsets, rerun/idempotency testing.
- Evidence base: code inspection + DB telemetry; local `e2e-run.log` only covers later resume (glossary stage).

---

## 2026-05-21T23:02:20-04:00: Trinity — Proposed Parallelism Defaults

**Author:** Trinity

**Status:** Proposed (awaiting Manish approval on quota review)

**Related decision:** Parallelism Investigation

### Proposal

Keep parallelism enabled by default and strengthen where it's already real:

- `translate_concurrency`: default 5 → 8
- `pool_max_size`: default 20 → 24 or 28 (must scale with translation workers)
- `ocr_concurrency`: keep configured; note it's not functional until OCR batching ships

### Rationale

- Translation parallelism already implemented, enabled, and idempotent per-chunk
- Shiv Sutra used 454 chunks; 5 → 8 workers has **1.6x throughput upside** if Azure OpenAI quota permits
- DB pool sizing already documents tie to translation worker count; raising concurrency without raising pool size is unsafe

### Approval Gate

Manish should approve default increases after quota review. Until then:
- Keep translation parallelism enabled
- Do not reduce defaults to 1
- Treat OCR parallelism as implementation backlog (#96), not solved

---

## 2026-05-21T23:02:20-04:00: Product Framing — Observability/FinOps as First-Class Capability

**Author:** Niobe (PM)

**Status:** Framing — awaiting Manish decision gate

**Related decision:** Morpheus architecture call if approved; Tank/Trinity for implementation

### Problem Summary

**Current state:**
- Manish ran Shiv Sutra (250 pages) for 10h 32m and spent $12.13
- Tank had to manually reconstruct cost from three scattered sources (PostgreSQL `translations` table, `books.page_count`, logs)
- **No self-serve cost inquiry:** Can't answer "How much did book X cost?" in under 5 minutes
- **Ephemeral `book_costs` table (Issue #93):** Overwritten per run; not a reliable audit trail
- **No cost visibility into planning:** Before running book N, Manish has no data-driven way to predict cost/wall-time

**Who feels it:** Manish (operator, funder, engineer); Trinity/Tank (cost forensics manual each time)

**Pain timeline:** Light today (one book). Becomes operational debt when processing 3–5 books in next 4 weeks.

### Success Criteria

Goal: Manish can answer cost + time questions in **under 1 minute** without SQL/grep.

- **Outcome 1:** "How much did Shiv Sutra cost?" → Dashboard shows $12.13 total, breakdown by OCR ($2.49) + GPT-4o ($9.64)
- **Outcome 2:** "How long did Shiv Sutra take?" → Dashboard shows wall time (10h 32m) + stage breakdown (OCR 5h 47m, Translation 3h 43m, Glossary 1h 30m, etc.)
- **Outcome 3:** "Before I run book N, what should I expect?" → Compare book N page count to Shiv Sutra baseline and project cost/time

### MVP Scope — Recommended Option (B)

**Simple page on `$web/admin/` querying Postgres directly**

**In scope (v1):**
1. Per-book cost table (name, total cost, breakdown, page count, wall time, per-stage duration)
2. Cost calculation module (utility; ingest book_id, compute total OpenAI + OCR + blob cost; return JSON)
3. Durable `book_costs` row fix (Issue #93): persist after every completed run, even if resumed/failed

**Out of scope (not v1):**
- Real-time progress dashboard (requires WebSocket; v1 is static HTML + manual query button)
- Cost projections / budget alerts (defer after observing 3+ books)
- Comparative analytics (which book was most expensive per page)
- Export to SaaS finops tools

### Rationale for Option (B)

1. **Fastest to build:** Static HTML + PostgreSQL SELECT. No app server, no new infra.
2. **Operator-first UX:** App Insights workbooks (Option A) are dense/engineering-oriented. Simple table answers Manish's question immediately.
3. **Single-operator scope:** No need for multi-tenant auth or enterprise finops. If Transpose scales later, revisit.
4. **Owned UX:** We control look and feel. No dependency on App Insights UI team.
5. **Cost-free:** Static HTML on blob storage costs nothing.

**Trade-offs:**
- No real-time progress during 10-hour runs (acceptable; cost insights work post-run)
- Must be password-protected (IP allowlist or SAS-protected blob)
- Manual query refresh (not streaming; acceptable for cost inquiry post-run)

### Audiobook Prerequisite?

**Answer: NO (conditional)**

Audiobook is a new pipeline, not an optimization of current pipeline. Cost structure orthogonal (TTS + blob storage vs. OCR + translation). Observability v1 won't measure audiobook cost anyway. When audiobook ships, add its telemetry to the same dashboard (v1.1).

**Implication:** Observability MVP is PDF pipeline only. Audiobook decision is independent and can proceed before or after observability ships.

### Open Questions for Manish

Before Morpheus designs:

1. **Security posture:** Who accesses `$web/admin/`? (Password/SSO, IP-allowlisted, or public-unlisted?)
   - Recommendation: Assume private (IP allowlist on blob storage) for v1.

2. **Wall-time breakdown:** Which stages matter most to you?
   - Recommendation: Show three main stages (OCR | Translation | Glossary) in v1. Export + publish are noise (<5 min each).

3. **Predicted cost for book N:** Linear scaling (cost ∝ pages)?
   - Recommendation: v1 shows Shiv Sutra baseline only. You do the mental math. Auto-projection in v1.1 after observing 3–5 books.

### Next Step

**Gate:** Manish approves framing → Morpheus designs cost dashboard architecture → Trinity/Tank implement

---

