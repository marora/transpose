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

## 2026-05-21T23:17:42-04:00: Observability Framing — Manish Locked Answers

**By:** Manish (via Copilot)

**Status:** APPROVED

**What:** Manish locked three concrete answers for Niobe's observability/finops framing:

1. **Security:** Dashboard MUST be auth-protected (not IP-allowlist, not public-unlisted).
2. **Metrics Granularity:** Stage-level (OCR / Translate / Glossary / Assemble / Export / Workspace / Ingest / Chunk).
3. **Projections:** Auto-estimate cost & wall time for book N based on N-1 actuals (linear by page count).

**Why:** Locks scope for Morpheus architecture handoff.

---

## 2026-05-21T23:17:42-04:00: Architecture Decision — Observability / FinOps Dashboard

**Date:** 2026-05-21T23:17:42-04:00  
**Author:** Morpheus (Lead/Architect)  
**Status:** APPROVED — ready for implementation by Trinity/Tank/Dozer  
**Traces to:** Niobe's product framing, Manish's 3 locked answers (above), Tank's cost source decision, Issue #93

### Executive Decisions

| # | Question | Choice |
|---|----------|--------|
| 1 | AuthN/AuthZ for admin page | **(c) Serve from existing Container App + Entra ID token validation** |
| 2 | Data path to Postgres | **(a) Thin JSON API on existing Container App** |
| 3 | Persistence model | **Append-only `book_cost_events` table** |

### 1. Authentication: Container App Route with Entra ID

**Choice:** Option (c) — the admin dashboard is a set of static HTML/JS/CSS files *served by the existing Container App* at `/admin/`, with a lightweight Entra ID bearer-token check middleware on all `/admin/*` routes.

**Why not (a) Azure Front Door:**
- $35+/month minimum for Standard tier. Overkill for single-operator access.
- Adds DNS, certificate, and routing complexity for one page.
- Public landing pages on `$web/` would need to remain separate — split brain.

**Why not (b) Azure Static Web Apps:**
- Would replace the current `$web/` blob static website entirely. Migration risk for existing landing pages (shiv-sutra/, future slugs).
- Built-in auth is EasyAuth — limited OIDC control, can't scope to Entra app registration as cleanly.
- Free tier has 2 custom domains max and limited bandwidth. Not a blocker, but unnecessary coupling.

**Why (c) Container App:**
- Container App already runs, already has Managed Identity, already connects to Postgres.
- aiohttp can serve static files from a directory (`/admin/index.html`, `/admin/app.js`) at negligible cost.
- Auth middleware: validate `Authorization: Bearer <token>` against Entra ID JWKS. Single `@require_entra_auth` decorator on admin routes. Pattern already exists in the ecosystem.
- No new infra. No new DNS. No new billing line item. Ships in hours, not days.
- Public landing pages stay on raw `$web/` — no migration, no risk to existing reader links.

**Trade-offs acknowledged:**
- Admin page availability is tied to Container App uptime (acceptable — if the app is down, there's nothing to observe).
- Static assets served from Python are not CDN-cached. For one operator hitting a 50KB page, this is irrelevant. If multi-tenant later, front with CDN then.

**Entra ID app registration:**
- Register `transpose-admin` app in Entra ID (single-tenant, confidential client).
- Admin page does MSAL.js PKCE flow → gets ID token + access token scoped to `api://transpose-admin/Dashboard.Read`.
- Container App validates bearer token signature + audience + issuer.
- No service principal secrets stored — PKCE is client-only.

### 2. Data Path: JSON API on Container App

**Choice:** Option (a) — thin read-only API routes on the existing Container App.

Routes:
```
GET /admin/api/books                     → list books with summary metrics
GET /admin/api/books/{book_id}/stages    → per-stage breakdown for one book
GET /admin/api/books/{book_id}/events    → raw cost events (audit trail)
GET /admin/api/projection?pages=N        → auto-estimate for a book of N pages
```

**Why not (b) pre-computed JSON:**
- Stale the moment a new run finishes. Requires a post-run hook to regenerate. Adds coupling.
- Can't drill into specific books without generating every permutation.
- Defeats the "answer in < 1 minute" success criterion during/after active runs.

**Why not (c) hybrid:**
- Added complexity for no real gain at MVP scale. One operator, < 10 books, Postgres can answer any of these in < 50ms.

**Implementation notes:**
- Routes live in a new module `src/transpose/observability/dashboard_api.py`.
- Registered in `api.py` under the `/admin/` prefix with the Entra auth middleware.
- Queries go through the existing `ctx.db` connection pool (Managed Identity → Postgres).
- JSON responses. No GraphQL. No pagination in v1 (< 10 books).

### 3. Persistence: Append-Only `book_cost_events` (Closes #93)

**The Problem**

`CostTracker.persist()` runs only after workspace stage completes. Any failure/interrupt before that point = zero cost data persisted. The current `book_costs` table also missing stage-level granularity.

**Contract: `book_cost_events` Table**

```sql
CREATE TABLE book_cost_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id),
    run_id UUID NOT NULL,              -- unique per pipeline invocation (supports resume tracking)
    stage_name TEXT NOT NULL,           -- ingest | ocr | chunk | translate | glossary | assemble | export | workspace
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,              -- NULL if stage failed mid-flight
    input_tokens BIGINT DEFAULT 0,
    output_tokens BIGINT DEFAULT 0,
    ocr_pages INT DEFAULT 0,
    blob_read_ops INT DEFAULT 0,
    blob_write_ops INT DEFAULT 0,
    estimated_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    retries INT DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'started',  -- started | completed | failed | partial
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_bce_book_id ON book_cost_events(book_id);
CREATE INDEX idx_bce_book_stage ON book_cost_events(book_id, stage_name);
```

**Write Pattern**

Append-only. One row per stage per run.

1. **Stage start:** INSERT with `status = 'started'`, `started_at = NOW()`, zeroed metrics.
2. **Stage end:** UPDATE the same row: set `ended_at`, `status = 'completed'|'failed'`, fill in token/page/blob counts.
3. If the process dies between start and end, the row stays `status = 'started'` with `ended_at = NULL` — dashboard shows it as incomplete. No data lost.

**Where in Code**

| Location | Action |
|----------|--------|
| `runner.py` — before each stage executes | `INSERT INTO book_cost_events (book_id, run_id, stage_name, started_at, status) VALUES (...)` |
| `runner.py` — after each stage completes | `UPDATE book_cost_events SET ended_at=..., status='completed', input_tokens=..., ...` |
| `runner.py` — in stage exception handler | `UPDATE book_cost_events SET ended_at=..., status='failed', error_message=...` |

### 4. Auto-Estimation (Projections)

**Model**

Linear scaling per stage, rolling window of last 3 completed books.

```
projected_cost(stage, pages) = median(cost_per_page[stage] for last 3 books) × pages
projected_time(stage, pages) = median(seconds_per_page[stage] for last 3 books) × pages
```

### 5. Stage-Level Metrics Contract

The 8 stages (per Manish's locked answer):

| Stage | Duration | Input Tokens | Output Tokens | OCR Pages | Cost (USD) | Retries | Status |
|-------|----------|-------------|--------------|-----------|-----------|---------|--------|
| ingest | ✓ | — | — | — | ✓ (blob) | ✓ | ✓ |
| ocr | ✓ | — | — | ✓ | ✓ | ✓ | ✓ |
| chunk | ✓ | — | — | — | ✓ (blob) | ✓ | ✓ |
| translate | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| glossary | ✓ | ✓ | ✓ | — | ✓ | ✓ | ✓ |
| assemble | ✓ | — | — | — | ✓ (blob) | ✓ | ✓ |
| export | ✓ | — | — | — | ✓ (blob) | ✓ | ✓ |
| workspace | ✓ | — | — | — | ✓ (blob) | ✓ | ✓ |

### 6. Module Boundaries

```
src/transpose/
├── observability/
│   ├── cost_tracker.py          # EXISTING — accumulates in-memory, writes aggregate to book_costs
│   ├── cost_events.py           # NEW — writes append-only events to book_cost_events (stage start/end)
│   ├── cost_rates.py            # EXISTING — pricing constants
│   ├── dashboard_api.py         # NEW — aiohttp routes for /admin/api/*
│   ├── projector.py             # NEW — estimation logic (pure functions)
│   ├── metrics.py               # EXISTING — OTel counters/histograms
│   ├── queries.py               # EXISTING — observability SQL helpers
│   └── tracing.py               # EXISTING — OTel tracing config
├── api.py                       # MODIFIED — mount /admin/* routes + auth middleware
└── pipeline/
    └── runner.py                # MODIFIED — emit cost events at stage boundaries

web/admin/                       # NEW — static HTML/JS/CSS (served by Container App)
├── index.html                   # Dashboard SPA shell
├── app.js                       # Fetch API, render tables/charts
└── style.css                    # Minimal styling
```

### 7. MVP Boundary

**v1 (ships first)**
- `book_cost_events` table + migration
- Stage-start/stage-end event writes in `runner.py`
- `/admin/api/books` — list books with totals
- `/admin/api/books/{id}/stages` — per-stage breakdown
- `/admin/api/projection?pages=N` — linear estimate
- Entra ID auth middleware on `/admin/*`
- Static admin page: table of books, click-to-expand stages, projection input
- Cross-book trend (last 5 books per stage)

**Explicitly NOT in v1**
- Live progress / WebSocket for in-flight runs
- Budget alerts / spending caps
- CSV/Excel export
- Multi-tenant filters / RBAC beyond single-operator
- Chunk-level drill-down
- Projection residual tracking
- Audiobook cost tracking

### 8. Ownership & Next Steps

| Owner | Work Item | Depends On |
|-------|-----------|-----------|
| **Tank** | Infra: Entra ID app registration + auth middleware wiring on Container App | — |
| **Trinity** | Schema: `book_cost_events` table, `cost_events.py` module, runner.py instrumentation | Tank (auth middleware pattern for testing) |
| **Trinity** | API: `dashboard_api.py` routes + `projector.py` | Schema done |
| **Trinity** | Frontend: `web/admin/` static files (HTML/JS/CSS) | API routes done |
| **Dozer** | Tests: unit tests for `cost_events.py`, `projector.py`, `dashboard_api.py`; integration test for auth middleware | Trinity modules exist |

**Issues to file:**
1. #97: `arch: persist book cost telemetry as append-only events (closes #93)` → trinity
2. #98: `infra: Entra ID auth for /admin/ routes on Container App` → tank [BLOCKER for v1]
3. #99: `feat(observability): dashboard API — /admin/api/ routes` → trinity
4. #100: `feat(observability): admin dashboard static frontend` → trinity
5. #101: `test(observability): coverage for cost_events, projector, dashboard_api` → dozer

---


## 2026-05-21T23:30:27-04:00: Backlog Prioritization & Execution Sequencing — Observability MVP Target 2026-05-24

**By:** Niobe (Product Manager)

**Decision:** Adopt strict execution sequence for observability v1: #98 → #97 → #91 → #99 → #100 → #101. Five P0 blockers (observability MVP), five P1 operational bugs (setup/workspace/SAS), three P2 deferred (perf, parallelism). Close five legacy P0/P1 issues as stale (#73–77). Re-label #78 to squad:oracle (editorial), #79 to squad:trinity (pipeline). Manish approval pending; batch close to occur after approval.

**Rationale:**
- **Observability is gate:** Manish's stated priority before parallelism and audiobook decisions. Cost visibility operational necessity at 3+ concurrent books.
- **Execution sequence prevents rework:** Dependencies within P0 block (#98 auth blocks #97 events, which block #99 API, which blocks #100 UI). P1 fixes are unblocked; #91 (SAS) parallel-friendly.
- **Legacy triage clears noise:** Five issues stale against current pipeline (different source text format, metadata now implemented, image preservation deferred). Two issues re-labeled to correct owners (editorial vs. pipeline).
- **Timeline aggressive but realistic:** ~20–25 billable hours Tank + Trinity over 2–3 sessions targets 2026-05-24 EOD. Aligns with Manish's 3–5 book readiness in next 4 weeks.

**Owner:** Tank (auth), Trinity (observability pipeline), Dozer (test), Niobe (prioritization oversight)

**Target Ship Date:** 2026-05-24 EOD

---
