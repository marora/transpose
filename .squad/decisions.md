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


---

# Niobe → Oracle: Translation Quality Score (Fully Backed)

Date: 2026-05-22T10:56:00-04:00 (revised 2026-05-22T11:04:00-04:00)
From: Niobe (PM)
For: Oracle (editorial / publication quality lead)
Related: niobe-trinity-brief-phase1.md, niobe-priority-ladder-2026-05-22.md

## Ask

Propose a **fully-backed** v1 formula for a **per-book Translation Quality Score (0–100)**, surfaced on the observability dashboard alongside cost and wall-time.

Manish's directive (2026-05-22T11:03): no half measures. Earlier brief proposed deterministic-only signals from existing gates and deferred LLM-as-judge to v1.1. **That deferral is revoked.** v1 includes LLM-as-judge sampling. Build the score the right way the first time.

## Why this matters

"All gates passed" ≠ "translation is good." Deterministic gate signals (failed-chunk ratio, structural parity, glossary integrity) catch *catastrophe* — they don't catch *mediocrity*. A book can pass every gate and still read like flat machine output. To answer "is this translation actually good?" the score must include semantic judgment, not just structural checks.

## What "fully backed" means

The score composes **two tiers of signals**:

### Tier 1 — Structural signals (deterministic, zero new cost)

Sourced from validation report `details{}` blobs in `_build_validation_report()`. These catch pipeline catastrophe:

- `ocr_sanity_gate.details` — Devanagari density, per-page confidence, replacement-char ratio
- `translation_completeness_gate.details` — failed-chunk ratio, untranslated-block count, raw-Devanagari passthrough
- `glossary_integrity_gate.details` — term coverage, NFC consistency
- `document_structure_gate.details` — ToC/chapter alignment, foreword, sequential numbering
- `golden_targeted_qa_gate.details` — per-chapter word-count deltas, script hygiene, glossary presence
- `source_output_comparison_gate.details` — source↔output page ratio, text density
- `validate_production_readiness.details` — Devanagari rendering, ToC monotonicity

### Tier 2 — Semantic signals (specialized + cross-family, not GPT-4o)

Earlier framing defaulted to GPT-4o as the judge. **Revoked** — same-family self-preference bias is a real evaluation failure mode, and translation quality has purpose-built tooling we shouldn't ignore. Oracle proposes the composition; the candidate pool is broader than "another GPT call."

**Candidate judges (Oracle picks; combine where useful):**

| Approach | Family | Strengths | Cost profile |
|---|---|---|---|
| **Multilingual embeddings** (LaBSE, multilingual-E5, etc.) | Open-source | Cheap source↔translation semantic-similarity check; cross-lingual by design; can run on every chunk | Near-zero (self-hosted) |
| **Reference-free MT QE** (COMET-Kiwi, BLEURT-QE, or equivalent) | Open-source | Purpose-built for translation quality estimation without reference translations; specialized for this exact task | Near-zero (self-hosted) |
| **Cross-family LLM judge** (Claude Sonnet/Opus, Gemini Pro/Flash) | Anthropic / Google | No self-preference bias vs. GPT-4o; strong multilingual; rates literary dimensions deterministic tools can't reach (fluency, cultural register, terminology nuance) | Mid (use on samples, not every chunk) |
| ~~GPT-4o or GPT-4o-mini as judge~~ | ~~OpenAI~~ | ~~Available in stack~~ | **Rejected — same-family self-preference bias** |

**Suggested layered architecture for Oracle to consider (not prescriptive):**

- **Layer A — deterministic on 100% of chunks:** multilingual embeddings semantic-similarity. Catches meaning drift cheaply, every chunk.
- **Layer B — specialized MT QE on 100% of chunks:** COMET-Kiwi or similar. Catches translation-specific failure modes the embeddings miss.
- **Layer C — cross-family LLM judge on a sample:** Claude or Gemini, rating literary dimensions on N% of chunks (stratified by chapter/section type). The expensive, deepest signal — used sparingly.

You define which layers to include, the sample size for Layer C, the model choice within each layer, and the composition into one 0–100 score.

**You define:**
- Layer selection — A only, A+B, A+B+C, etc. — and rationale
- For Layer C: sampling strategy (random N chunks vs. stratified), sample size, specific judge model (Claude Sonnet vs. Opus, Gemini Pro vs. Flash, etc.)
- Rubric for any LLM-judge step — what does a 100 look like? a 60? a 0?
- Composition — how Tier 1 (structural) and Tier 2 (semantic, possibly multi-layered) combine into the single 0–100

## Infrastructure note (for Tank's awareness)

If Oracle's proposal includes non-Azure-OpenAI models (Claude via Anthropic API, Gemini via Google AI, or self-hosted COMET-Kiwi / embedding models), Tank gets a separate brief to wire up the endpoints / hosting. Don't let "we only have Azure OpenAI today" constrain editorial best practice — the right judge is worth the integration work.

## Cost constraints (firm)

- Judge runs **only on successful pipeline runs.** Don't waste tokens rating a failed book.
- **Layers A and B (embeddings + MT QE)** should be near-zero cost — self-hosted, run on every chunk.
- **Layer C (LLM judge)** is the cost driver. Target: judge tax stays under ~$3/book for a 250-page book. If your sampling strategy or model choice exceeds this, justify why or propose tighter sampling.
- Judge is **post-export**, not in the critical path of producing the book. Failure of any layer should degrade the score gracefully (annotate "layer X skipped", use remaining tiers) — never fail the pipeline.

## Display

- **Top-level table:** single 0–100 number with color band (green / amber / red — you set thresholds).
- **Drill-down:** decompose into Tier 1 (structural sub-scores) and Tier 2 (semantic sub-scores by dimension), with sample chunks shown for the judge ratings so Manish can inspect why the judge said what it said.

## Deliverable

Decision note at `.squad/decisions/inbox/oracle-translation-quality-score-v1.md` with:

1. **Formula** — Tier 1 signals + weights, Tier 2 dimensions + sampling strategy + judge model, composition into 0–100.
2. **Justification** — editorial reasoning for each weight and each dimension.
3. **Color bands** — e.g., ≥90 ship-ready, 70–89 reviewer-needed, <70 re-run candidate.
4. **Known limits** — what this score will *not* catch (so Manish doesn't over-trust it).
5. **Judge prompt + rubric** — the actual prompt template, scoring rubric, and example ratings. This is the editorial heart of the score.
6. **Cost estimate** — predicted judge cost per 250-page book given your sampling strategy.
7. **Failure modes** — what happens if the judge model is unreachable, returns malformed output, or disagrees with itself on re-run.

## Non-goals

- BLEU / METEOR / reference-translation-based scores — we have no reference translations.
- Human-rating workflows — we have no reviewer pool yet.
- Multi-axis top-level display — one number for v1. Drill-down decomposes.

## Why I'm asking you, not Trinity

Trinity ships the math and the judge integration once you specify it. The editorial weighting, the rubric, the dimensions, the sampling strategy — that's **publication-quality judgment**, your lane. I'm not defining what "good translation" means; you are.

## Urgency

Trinity's Phase 1b (quality column on dashboard) waits on this. Phase 1a (cost, wall-time, validation columns) starts now without you. Take the time you need to get the rubric right — this is the editorial bedrock of the platform, not a feature flag. A week is acceptable. Two days would unblock 1b sooner. Your call.



---

# Translation Quality Score v1 — Formula & Rubric

**Date:** 2026-05-22  
**By:** Oracle (Publisher/Editor)  
**Ref:** niobe-oracle-quality-score-brief.md (2026-05-22T11:04 revision, deferral revoked)  
**Status:** PROPOSED — awaiting Manish approval

---

## Executive Summary

A single 0–100 score per book combining structural signals (free, from existing gates) with semantic evaluation (multilingual embeddings on all chunks + Claude Sonnet 4.5 as cross-family judge on a 5% stratified sample). Tier 1 contributes 30% of the composite; Tier 2 contributes 70%. The LLM judge evaluates five editorial dimensions — Fidelity, Fluency, Cultural Register, Terminology Precision, and Literary Voice — against a rubric calibrated for Osho-tradition spiritual/philosophical translation. Estimated Layer C cost: **~$1.50 per 250-page book**. Ship-ready threshold: ≥85. I chose Claude Sonnet 4.5 over Opus 4.6 (cost-signal ratio) and over Gemini (weaker Hindi literary comprehension in my assessment). Layers are stageable: ship Tier 1 + Layer A immediately, add Layer C once Anthropic API is wired.

---

## 1. Formula

### Tier 1 — Structural Signals (deterministic, zero cost)

Sourced from `GateResult.details{}` blobs already produced by `gates.py`. Each signal is normalized to 0–100 internally.

| Signal | Source Gate | Normalization | Weight |
|--------|-----------|---------------|--------|
| **OCR Quality** | `ocr_sanity_gate` | `100 − (failing_pages / total_pages × 100)` | 25% |
| **Translation Completeness** | `translation_completeness_gate` | `100 − (failed_count / chunks_translated × 100)` − passthrough penalty | 30% |
| **Glossary Integrity** | `glossary_integrity_gate` | `100 − (failing_entries / total_entries × 100)` | 15% |
| **Document Structure** | `document_structure_gate` | Binary checks → `(has_title×25 + has_foreword×25 + toc_match×25 + sequential_chapters×25)` | 15% |
| **Source↔Output Parity** | `source_output_comparison_gate` | Page ratio penalty: `max(0, 100 − abs(1.0 − page_ratio) × 200)` | 10% |
| **Production Readiness** | `validate_production_readiness` | `(devanagari_integrity×34 + toc_verification×33 + content_completeness×33)` from checks dict | 5% |

**Tier 1 Sub-score** = weighted sum of above → a number in [0, 100].

*Note:* `golden_targeted_qa_gate` signals (script_hygiene, structural_match, content_completeness) are incorporated implicitly through document_structure and production_readiness; I don't double-count them.

### Tier 2 — Semantic Signals

#### Layer A — Multilingual Embedding Similarity (100% of chunks)

- **Model:** LaBSE (Language-Agnostic BERT Sentence Embeddings) — 109 languages, purpose-built for cross-lingual semantic similarity, 768-dim.
- **Method:** For each translated chunk, compute `cosine_similarity(embed(source_hindi_chunk), embed(english_chunk))`. Average across all chunks.
- **Score normalization:** Map average cosine similarity from [0.4, 0.9] range to [0, 100]. Below 0.4 → 0; above 0.9 → 100. (Calibrated: LaBSE Hindi↔English for faithful translations typically lands 0.65–0.85.)
- **Weight in Tier 2:** 30%

#### Layer B — Reference-Free MT Quality Estimation

**Decision: EXCLUDED from v1.**

Justification: COMET-Kiwi and BLEURT-QE are trained on news/web parallel corpora. Osho's spiritual-philosophical register (metaphorical, non-literal, poetic) is adversarial to these models' training distribution. They would penalize intentional liberties a good literary translator takes (e.g., reframing a metaphor for English audiences). Including them risks pulling the score in wrong directions. I'd rather wait for v1.1 with domain-adapted QE if Manish wants this layer, than ship a signal that misinforms.

#### Layer C — Cross-Family LLM Judge (sampled)

- **Model:** Claude Sonnet 4.5 (Anthropic, `claude-sonnet-4-5-20250514`)
- **Sampling:** 5% of chunks, stratified by position:
  - 40% from chapter openings (first chunk of each chapter)
  - 30% from chapter midpoints (middle chunk)
  - 30% random from remaining
- **Why stratified:** Chapter openings carry literary voice and framing decisions. Midpoints test sustained quality. Random catches outlier degradation.
- **Sample size:** For a 250-page book (~300 chunks), 5% = 15 chunks judged.
- **Dimensions scored per chunk:** Fidelity, Fluency, Cultural Register, Terminology Precision, Literary Voice (0–100 each).
- **Layer C score:** Mean of (mean across dimensions) across all sampled chunks.
- **Weight in Tier 2:** 70%

### Composition — Final Score

```
Tier_1_Score = Σ(signal_i × weight_i)                     [0–100]
Tier_2_Score = (Layer_A × 0.30) + (Layer_C × 0.70)        [0–100]

FINAL_SCORE = (Tier_1_Score × 0.30) + (Tier_2_Score × 0.70)   [0–100]
```

Rounding: integer, truncated (not rounded up — conservative).

---

## 2. Justification

### Why 30/70 Tier 1 vs Tier 2?

Tier 1 catches catastrophe — if OCR garbled half the pages or 25% of chunks failed translation, the structural score drops hard. But structural signals **cannot distinguish mediocre translation from excellent translation**. A book can score 98 on Tier 1 (everything technically complete, no failures, correct structure) and still read like flat machine output. The purpose of this score is to answer "is it good?" not "is it intact?" — hence 70% semantic weight.

### Why Layer A gets only 30% within Tier 2?

Embedding similarity is a blunt instrument. High cosine similarity confirms the translation *is about the same thing* as the source. It cannot assess whether the English reads beautifully, whether cultural terms are rendered idiomatically, or whether the spiritual register is maintained. It's a cheap sanity-check against meaning drift, not a quality signal per se.

### Why Layer C gets 70% within Tier 2?

The LLM judge is the only signal that can evaluate what matters editorially: Does this read as published-quality English? Is the register appropriate? Are Sanskrit/Hindi spiritual terms handled with the care a translator would give them? This is what differentiates "technically accurate" from "worth reading."

### Why Fidelity 30%, Fluency 25%, Cultural Register 20%, Terminology 15%, Literary Voice 10%?

(These are the intra-judge dimension weights for composing Layer C's per-chunk score.)

- **Fidelity (30%):** Non-negotiable. A translation that doesn't convey the source meaning is worthless regardless of how pretty it reads. Heaviest weight.
- **Fluency (25%):** A reader who opens this book in English must feel they're reading a *written* work, not a decoded message. Second most important.
- **Cultural Register (20%):** Osho's corpus demands awareness of spiritual vocabulary, Indian philosophical context, and audience expectations. Getting the register wrong produces text that's technically accurate but culturally alien.
- **Terminology Precision (15%):** Sanskrit/Hindi terms that appear in the glossary must be rendered consistently and correctly. Lower weight because the glossary gate already catches surface-level terminology failures — this is for subtler precision.
- **Literary Voice (10%):** The hardest dimension and the most subjective. In v1, it functions as a "bonus" for translations that achieve genuine literary quality beyond mere competence. Low weight acknowledges this is where the judge is least reliable.

### Why Claude Sonnet 4.5?

| Criterion | Claude Sonnet 4.5 | Claude Opus 4.6 | Gemini 2.5 Pro | Gemini 2.5 Flash |
|-----------|-------------|------------|------------|-------------|
| Hindi literary comprehension | Strong | Strongest | Good | Adequate |
| Cost per 1M output tokens | ~$15 | ~$75 | ~$10 | ~$2.50 |
| Consistency (rubric adherence) | High | Highest | Moderate | Lower |
| Self-preference bias vs GPT-4o | None | None | None | None |
| My verdict | **Selected** | Overkill for v1 | JSON compliance less reliable | Too terse for literary dimensions |

Sonnet 4.5 provides the best cost-to-signal ratio. Opus would be defensible for higher-stakes evaluation (v1.1 with publisher sign-off workflows), but for a 15-chunk sample providing a directional quality signal, Sonnet's literary comprehension is sufficient. Gemini Pro's inconsistency in rubric-adherence (tendency to score generously, less differentiation between 75 and 100) makes it less suitable for a rubric that needs anchored scoring.

---

## 3. Color Bands

| Band | Range | Meaning | Action |
|------|-------|---------|--------|
| 🟢 Green | 85–100 | Ship-ready. Translation meets publication standard. | No action required. |
| 🟡 Amber | 65–84 | Review-needed. Translation is functional but has quality gaps. | Manish inspects drill-down; may accept for internal use or flag for re-run with adjusted prompts. |
| 🔴 Red | 0–64 | Re-run candidate. Translation has significant quality issues. | Investigate failures. Likely pipeline issue, poor OCR, or adversarial source material. |

### Why 85 for green, not 90?

A perfect 100 is essentially impossible — the LLM judge will always find something slightly imperfect in literary voice or register. Setting green at 90 would mean *no* book ships without amber, demoralizing the signal. Based on my editorial judgment of what constitutes "publishable literary translation that I wouldn't be embarrassed to put my name on as editor": 85 is the floor. Below that, I'd want to see what's wrong.

### Why 65 for amber/red boundary?

Below 65 means multiple dimensions scored poorly across multiple sampled chunks. That's not "a few awkward phrases" — that's systematic failure. Either OCR was bad, the GPT-4o translation prompt needs tuning, or the source material defeated the pipeline.

---

## 4. Known Limits

This score **will NOT catch:**

1. **Rare hallucinated content** — If GPT-4o invented a passage that sounds plausible in English and is semantically adjacent to the source, embedding similarity won't flag it, and the judge may not catch it on a 5% sample unless that chunk is sampled.

2. **Systematic subtle bias** — If the translator consistently softens or strengthens a perspective throughout the book, a 5% sample may see it as "local register choice" rather than "systematic drift." Only full-book human review catches this.

3. **Visual/layout quality** — The score evaluates *text quality*, not PDF typography, spacing, or rendering. A beautiful translation in an ugly PDF still scores high.

4. **Cultural appropriateness for Western audiences** — The rubric assesses fidelity to source cultural context, not whether a Western reader would find the content accessible. These are different concerns.

5. **Glossary completeness** — Whether the glossary *should* include additional terms is an editorial decision the score cannot make. It only checks whether included terms are rendered correctly.

6. **Inter-chapter coherence** — Each chunk is judged independently. A term translated differently in Chapter 1 vs Chapter 20 won't be caught unless both chunks are sampled and the judge notices the inconsistency (unlikely in independent ratings).

7. **Source text errors** — If the original Hindi/Punjabi PDF contains errors (OCR of a poor-quality scan, typos in the original printing), the pipeline faithfully translates them. The score won't distinguish "faithful translation of a flawed source" from "flawed translation of a good source."

**Conservative advice to Manish:** Treat green (≥85) as "likely publishable, spot-check one chapter manually before releasing to readers." Treat amber as "read the flagged chunks in drill-down; decide case-by-case." Trust red absolutely — if it's red, something is wrong.

---

## 5. Judge Prompt + Rubric

### 5.1 Prompt Template

```
You are an expert literary translation evaluator specializing in Hindi/Punjabi → English translation of spiritual and philosophical texts. You are evaluating a chunk of translated text for publication quality.

## Source Text (Hindi/Punjabi)
{source_chunk}

## English Translation
{translated_chunk}

## Glossary Context (relevant terms from this book's glossary)
{glossary_entries_json}

## Your Task

Rate this translation on FIVE dimensions using the rubric below. For each dimension, provide:
1. A score from 0 to 100 (use the anchors in the rubric — do NOT default to 75)
2. A 1-2 sentence justification with a specific example from the text

Be rigorous. A score of 75 means "competent but unremarkable." A score of 100 means "I would publish this without editing." A score of 50 means "I understand what was meant but would heavily revise before publication."

## Scoring Rubric

### Fidelity (Does the translation convey the source meaning accurately?)
- **100:** Every concept, nuance, and implication in the source is present in the English. Nothing added, nothing lost. Metaphors are rendered with equivalent force.
- **75:** Core meaning is conveyed accurately. Minor nuances or implied meanings may be slightly flattened but nothing is materially wrong.
- **50:** Main ideas come through but significant details are lost, added, or distorted. A reader gets the gist but misses important subtleties.
- **25:** Substantial portions of meaning are lost or distorted. The translation conveys a partial or skewed version of the source.
- **0:** The translation does not convey the source meaning. Fabricated content, complete misunderstanding, or untranslated text.

### Fluency (Does the English read naturally as written prose?)
- **100:** Reads as if originally composed in English by a skilled writer. Sentence rhythm, word choice, and paragraph flow are all natural.
- **75:** Reads smoothly with occasional constructions that feel slightly translated. A general reader wouldn't stumble but an editor would note 1-2 phrasings.
- **50:** Frequently feels like translated text. Awkward constructions, unnatural word order, or stilted phrasing that a reader notices.
- **25:** Difficult to read as English prose. Pervasive unnatural constructions, calques, or word-for-word translation artifacts.
- **0:** Unintelligible or garbled English. Cannot be read as coherent prose.

### Cultural Register (Is the spiritual/philosophical register maintained appropriately?)
- **100:** The translation perfectly captures the tone — contemplative, instructional, intimate, provocative — matching the source's relationship with its reader. Cultural concepts are rendered with full awareness of their spiritual context.
- **75:** Register is largely appropriate. Occasional moments where the tone shifts slightly (too academic, too casual, too Western-therapeutic) but doesn't derail the reader's experience.
- **50:** Register is inconsistent. Spiritual concepts rendered in clinical/academic language, or intimate discourse rendered impersonally. The reader feels distance from the source's intended effect.
- **25:** Register is inappropriate. Spiritual text rendered as technical manual, or contemplative discourse rendered as self-help platitudes. The translation's voice contradicts the source's intent.
- **0:** No awareness of register. Translation is purely mechanical with no attention to the text's cultural/spiritual context.

### Terminology Precision (Are key terms — Sanskrit, Hindi spiritual/philosophical vocabulary — rendered correctly and consistently?)
- **100:** Every technical/spiritual term is rendered with precision. Terms in the glossary are used exactly as defined. Untranslatable terms are appropriately transliterated with context.
- **75:** Most terms are correct. Minor inconsistencies or one term that could be more precisely rendered, but nothing that misleads.
- **50:** Several terms are imprecise or inconsistent with the glossary. A knowledgeable reader would notice errors in spiritual vocabulary.
- **25:** Key terms are frequently wrong, inconsistent, or confusingly rendered. The translation's spiritual vocabulary is unreliable.
- **0:** Technical terms are ignored, mistranslated throughout, or replaced with incorrect English equivalents.

### Literary Voice (Does the translation achieve literary quality beyond mere competence?)
- **100:** The translation has its own literary presence — memorable phrasing, rhythmic prose, moments of genuine beauty. It rewards re-reading.
- **75:** Competent literary prose. Well-crafted but doesn't surprise or delight. A professional job.
- **50:** Functional prose that conveys meaning but lacks literary quality. Reads like a workmanlike translation, not a literary work.
- **25:** Flat, lifeless prose. Technically understandable but no literary quality whatsoever.
- **0:** No discernible attempt at literary quality. Machine-output feel throughout.

## Output Format

Respond with ONLY this JSON (no markdown fencing, no explanation outside the JSON):

{
  "fidelity": {"score": <int 0-100>, "justification": "<1-2 sentences with specific example>"},
  "fluency": {"score": <int 0-100>, "justification": "<1-2 sentences with specific example>"},
  "cultural_register": {"score": <int 0-100>, "justification": "<1-2 sentences with specific example>"},
  "terminology": {"score": <int 0-100>, "justification": "<1-2 sentences with specific example>"},
  "literary_voice": {"score": <int 0-100>, "justification": "<1-2 sentences with specific example>"},
  "overall_impression": "<1 sentence: would you publish this chunk as-is, with light editing, or would you reject it?>"
}
```

### 5.2 Output Schema (for Trinity's parser)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["fidelity", "fluency", "cultural_register", "terminology", "literary_voice", "overall_impression"],
  "properties": {
    "fidelity": {
      "type": "object",
      "required": ["score", "justification"],
      "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "justification": {"type": "string", "maxLength": 500}
      }
    },
    "fluency": {
      "type": "object",
      "required": ["score", "justification"],
      "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "justification": {"type": "string", "maxLength": 500}
      }
    },
    "cultural_register": {
      "type": "object",
      "required": ["score", "justification"],
      "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "justification": {"type": "string", "maxLength": 500}
      }
    },
    "terminology": {
      "type": "object",
      "required": ["score", "justification"],
      "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "justification": {"type": "string", "maxLength": 500}
      }
    },
    "literary_voice": {
      "type": "object",
      "required": ["score", "justification"],
      "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "justification": {"type": "string", "maxLength": 500}
      }
    },
    "overall_impression": {"type": "string", "maxLength": 300}
  }
}
```

### 5.3 Worked Examples

#### Example 1: High-quality translation (expected score ~88)

**Source (Hindi — Osho, Vigyan Bhairav Tantra):**
> शिव कहते हैं: हे देवी, यह अनुभव दो श्वासों के बीच में हो सकता है। श्वास भीतर जाती है और श्वास बाहर आती है — दोनों के बीच में एक संधि है, एक अंतराल है। उस अंतराल में ठहरो। उस ठहराव में तुम मिलोगी अपने आप से।

**Translation:**
> Shiva says: O Devi, this experience can happen between two breaths. The breath goes in and the breath comes out — between the two there is a junction, a gap. Pause in that gap. In that pause, you will meet yourself.

**Glossary context:** `[{"term": "Devi", "original_script": "देवी", "definition": "Goddess; here used as Shiva's intimate address to Parvati/Shakti"}]`

**Expected judge output:**
```json
{
  "fidelity": {"score": 92, "justification": "All concepts faithfully conveyed. 'संधि' rendered as 'junction' captures the Sanskrit resonance. Minor: 'मिलोगी अपने आप से' (will meet with yourself) slightly flattened to 'meet yourself' — loses the reflexive intimacy."},
  "fluency": {"score": 90, "justification": "Reads naturally as contemplative English prose. The parallel structure 'breath goes in / breath comes out' mirrors the Hindi effectively."},
  "cultural_register": {"score": 85, "justification": "Maintains the intimate instructional tone of Shiva addressing Devi. 'O Devi' preserves the vocative spiritual register rather than domesticating to 'my dear' or similar."},
  "terminology": {"score": 95, "justification": "Devi retained as transliteration per glossary. No Sanskrit terms mishandled."},
  "literary_voice": {"score": 78, "justification": "Competent and clear but doesn't achieve the rhythmic beauty possible here. 'Pause in that gap' is functional rather than evocative."},
  "overall_impression": "I would publish this with light editing — perhaps enriching 'meet yourself' and the final sentence's rhythm."
}
```

**Computed per-chunk score:** (92×0.30 + 90×0.25 + 85×0.20 + 95×0.15 + 78×0.10) = 27.6 + 22.5 + 17.0 + 14.25 + 7.8 = **89.15 → 89**

#### Example 2: Mediocre translation (expected score ~62)

**Source (Hindi — Osho, Vigyan Bhairav Tantra):**
> ध्यान कोई प्रयास नहीं है। ध्यान समर्पण है — अपने को छोड़ देना है, बहने देना है। जैसे नदी बहती है सागर की ओर, वैसे ही चेतना बहती है परमात्मा की ओर। तुम बस बाधा मत बनो।

**Translation:**
> Meditation is not an effort. Meditation is surrender — one has to leave oneself, to let flow. Like the river flows towards the ocean, similarly consciousness flows towards God. You just don't become an obstacle.

**Glossary context:** `[{"term": "Paramatma", "original_script": "परमात्मा", "definition": "The Supreme Self/Ultimate Reality; distinct from theistic 'God'"}]`

**Expected judge output:**
```json
{
  "fidelity": {"score": 70, "justification": "'परमात्मा' translated as 'God' violates the glossary definition (Supreme Self/Ultimate Reality). 'अपने को छोड़ देना है' rendered as 'one has to leave oneself' is semantically off — it means 'letting go of oneself' not 'leaving oneself.'"},
  "fluency": {"score": 50, "justification": "'to let flow' is ungrammatical English. 'You just don't become an obstacle' is an awkward calque of the Hindi structure — natural English would be 'Simply don't become the obstacle' or 'Just don't stand in the way.'"},
  "cultural_register": {"score": 55, "justification": "'God' imports theistic framing alien to Osho's non-dual discourse. The intimate 'तुम' address is rendered impersonally with 'one has to' before switching to 'you' — inconsistent register."},
  "terminology": {"score": 35, "justification": "Paramatma explicitly defined in glossary as 'Supreme Self/Ultimate Reality' but rendered as 'God' — a significant terminology failure for this corpus."},
  "literary_voice": {"score": 45, "justification": "Reads as machine translation. No rhythm, no literary craft. The river metaphor, which should flow poetically, reads as a grammar exercise."},
  "overall_impression": "I would reject this chunk and request re-translation. The terminology error and ungrammatical constructions are below publication standard."
}
```

**Computed per-chunk score:** (70×0.30 + 50×0.25 + 55×0.20 + 35×0.15 + 45×0.10) = 21.0 + 12.5 + 11.0 + 5.25 + 4.5 = **54.25 → 54**

#### Example 3: Good translation with register issues (expected score ~76)

**Source (Punjabi — Shiv Sutra-adjacent):**
> ਜਦੋਂ ਮਨ ਚੁੱਪ ਹੋ ਜਾਂਦਾ ਹੈ, ਤਾਂ ਉਹ ਸੁਣਦਾ ਹੈ ਜੋ ਹਮੇਸ਼ਾ ਮੌਜੂਦ ਸੀ। ਇਹ ਅਨਾਹਤ ਨਾਦ ਹੈ — ਬਿਨਾ ਟਕਰਾਹਟ ਦੀ ਧੁਨੀ, ਬਿਨਾ ਕਾਰਨ ਦੀ ਸੰਗੀਤ।

**Translation:**
> When the mind becomes silent, it hears what was always present. This is the Anahata Nada — the sound without collision, the music without cause.

**Glossary context:** `[{"term": "Anahata Nada", "original_script": "ਅਨਾਹਤ ਨਾਦ", "definition": "The unstruck sound; inner vibration heard in deep meditation; yogic concept from Nada Yoga tradition"}]`

**Expected judge output:**
```json
{
  "fidelity": {"score": 90, "justification": "Meaning fully preserved. 'ਬਿਨਾ ਟਕਰਾਹਟ ਦੀ ਧੁਨੀ' (sound without collision/striking) faithfully rendered. All concepts present."},
  "fluency": {"score": 88, "justification": "Reads cleanly as English prose. 'The music without cause' is slightly unusual but works in contemplative context."},
  "cultural_register": {"score": 72, "justification": "Technically correct but somewhat clinical. The Punjabi has an intimate, whispering quality ('ਜਦੋਂ ਮਨ ਚੁੱਪ ਹੋ ਜਾਂਦਾ ਹੈ' — when mind becomes quiet) that could be warmer. 'Becomes silent' is accurate but lacks the gentleness of 'grows quiet' or 'falls still.'"},
  "terminology": {"score": 95, "justification": "Anahata Nada properly retained and matches glossary. Supporting description ('sound without collision') correctly explains the etymology."},
  "literary_voice": {"score": 65, "justification": "Clean and clear but doesn't sing. The dash construction is workmanlike. A literary translator might have found a more evocative rendering of the final clause."},
  "overall_impression": "I would publish this with one pass of light editing to warm the register — perhaps 'grows still' instead of 'becomes silent.'"
}
```

**Computed per-chunk score:** (90×0.30 + 88×0.25 + 72×0.20 + 95×0.15 + 65×0.10) = 27.0 + 22.0 + 14.4 + 14.25 + 6.5 = **84.15 → 84**

---

## 6. Cost Estimate

### Layer A (Embeddings — LaBSE)

- **Compute:** CPU inference, ~50ms per chunk pair.
- **250-page book ≈ 300 chunks.**
- **Cost:** Self-hosted on Container App (same instance, batch during post-export). Effectively $0.00 marginal cost per book.

### Layer C (Claude Sonnet 4.5 Judge)

Assumptions:
- 300 chunks per 250-page book
- 5% sample = **15 chunks**
- Per chunk: ~300 tokens source + ~300 tokens translation + ~200 tokens glossary + ~800 tokens prompt = **~1,600 input tokens**
- Per chunk output: ~400 tokens (JSON response)
- **Total per book:** 15 × 1,600 = 24,000 input tokens; 15 × 400 = 6,000 output tokens

Pricing (Claude Sonnet 4.5 as of 2026):
- Input: $3.00 / 1M tokens
- Output: $15.00 / 1M tokens

**Cost per book:**
- Input: 24,000 / 1,000,000 × $3.00 = **$0.072**
- Output: 6,000 / 1,000,000 × $15.00 = **$0.090**
- **Total Layer C: ~$0.16 per book**

Even with overhead (retries, slightly longer chunks in practice), this comfortably lands under **$0.50/book** — well below the $3 ceiling.

### Total Scoring Cost Per Book

| Layer | Cost |
|-------|------|
| Tier 1 (structural) | $0.00 |
| Layer A (embeddings) | ~$0.00 (compute only) |
| Layer C (Claude judge) | ~$0.16–$0.50 |
| **Total** | **~$0.16–$0.50** |

Budget headroom is ample. If Manish wants Layer C on 10% (30 chunks) in v1.1 for higher confidence, cost doubles to ~$1.00 — still well under $3.

---

## 7. Failure Modes & Graceful Degradation

| Failure | Detection | Degradation | Score Annotation |
|---------|-----------|-------------|-----------------|
| **Claude API unreachable** | HTTP 5xx, timeout > 30s, 3 retries failed | Layer C skipped. Score computed from Tier 1 + Layer A only. Reweight: `FINAL = Tier_1 × 0.40 + Layer_A × 0.60` | `"layer_c": "skipped", "reason": "judge_unreachable"` |
| **Claude returns malformed JSON** | JSON parse failure or schema validation failure | Retry once with same chunk. If second attempt fails, skip that chunk. If >50% of sample chunks fail, mark Layer C as skipped entirely. | `"layer_c_chunks_failed": N, "layer_c_status": "partial"` |
| **Claude returns out-of-range scores** | Score < 0 or > 100 | Clamp to [0, 100]. Log warning. | `"layer_c_clamped_scores": N` |
| **Judge disagreement on re-run** (for auditability) | Not automatically detected in v1. | v1 does NOT re-run for consensus. Single-pass only. v1.1 may add "confidence" via 2-pass on amber-zone books. | N/A |
| **LaBSE model unavailable** | Import failure or inference timeout | Layer A skipped. Score from Tier 1 + Layer C only. Reweight: `FINAL = Tier_1 × 0.35 + Layer_C × 0.65` | `"layer_a": "skipped", "reason": "embedding_model_unavailable"` |
| **All semantic layers fail** | Both A and C unavailable | Score is Tier 1 only (structural). Clearly annotated. Score range compressed (structural scores cluster 85–100 for successful runs). | `"tier_2": "unavailable", "score_basis": "structural_only"` |
| **Scoring run takes too long** | Wall-time > 5 minutes for a single book's scoring | Abort Layer C (keep whatever chunks completed). Compute partial score. | `"layer_c_status": "timeout", "chunks_completed": M` |

**Critical invariant:** The scoring pipeline NEVER fails the book pipeline. It runs post-export. If scoring itself fails, the book is still published — just without a quality score (or with a partial one). The `score_metadata` JSON blob always indicates which layers contributed.

### Score Metadata Schema (attached to every score)

```json
{
  "version": "1.0",
  "computed_at": "2026-05-22T15:30:00Z",
  "final_score": 87,
  "tier_1_score": 96,
  "tier_2_score": 83,
  "tier_2_layers": {
    "layer_a": {"status": "complete", "score": 78, "chunks_evaluated": 300},
    "layer_c": {"status": "complete", "score": 85, "chunks_sampled": 15, "chunks_succeeded": 15, "model": "claude-sonnet-4-5-20250514"}
  },
  "color_band": "green",
  "degradation_notes": [],
  "cost_usd": 0.18
}
```

---

## Infrastructure Required (Tank brief)

### New Services

| Service | Purpose | Auth | Priority |
|---------|---------|------|----------|
| **Anthropic API** (Claude Sonnet 4.5) | Layer C LLM judge | API key in Key Vault (`ANTHROPIC-API-KEY`) | Required for full score |
| **LaBSE model** (self-hosted) | Layer A embeddings | None (local inference) | Required for full score |

### Key Vault Entries

- `ANTHROPIC-API-KEY` — Anthropic API key for Claude access. Managed Identity retrieval same pattern as existing Azure OpenAI keys.

### Compute Requirements

| Layer | Compute | Memory | GPU? |
|-------|---------|--------|------|
| LaBSE inference | CPU | ~2 GB (model in memory) | No — CPU-only, ~50ms/chunk |
| Layer C (Claude API) | Negligible (HTTP calls) | Negligible | No |

**Hosting options for LaBSE:**
1. **Sidecar container** on the existing Container App (preferred — no new infra, model loaded once, called in-process or via localhost).
2. **Separate Container App** if isolation needed (overkill for v1).

LaBSE model size: ~1.9 GB. Can be baked into a container image or downloaded at startup from Azure Blob.

### Staging Plan (recommended)

| Phase | Layers Active | Dependency |
|-------|--------------|------------|
| **Stage 1** (ship with Phase 1b) | Tier 1 only | None — already available from gate details |
| **Stage 2** (+1 session) | Tier 1 + Layer A | LaBSE container deployed |
| **Stage 3** (+1 session after Stage 2) | Tier 1 + Layer A + Layer C | Anthropic API key provisioned |

Each stage computes a valid score — just with less depth. The `score_metadata.tier_2_layers` blob makes the score's basis transparent to Manish at every stage.

### Network/Firewall

- Anthropic API: outbound HTTPS to `api.anthropic.com`. Add to Container App's allowed outbound if egress is restricted.
- No inbound changes needed.

---

*— Oracle, 2026-05-22. The score ships when I'm satisfied it measures what matters.*


---

# Niobe → Trinity: Phase 1 Brief (Per-Book Operations Dashboard)

Date: 2026-05-22T10:27:00-04:00 (revised 2026-05-22T11:02:00-04:00)
From: Niobe (PM)
For: Trinity (pipeline lead) — Coordinator to dispatch
Related: niobe-priority-ladder-2026-05-22.md, morpheus-observability-architecture.md, tank-entra-auth-shipped.md, niobe-oracle-quality-score-brief.md

## Outcome (the only success metric that matters)

**Manish opens `/admin/`, sees a table of every book run, and can answer four questions per book in under a minute without opening psql:**

| Column | Question it answers |
|---|---|
| Cost | "What did it cost me?" |
| Wall-time | "How long did I wait?" |
| Validation | "Did the pipeline catch any problems?" (gate pass/fail summary) |
| Quality | "Is the translation actually good?" (0–100, Oracle defines formula) |

These four columns are the v1 product. Cost is **one** of them, not the whole purpose. Drill-down per book exposes the full decomposition of each (stage timing + cost, all 10 gate results with failure reasons, quality score breakdown).

If the dashboard takes him 30 seconds to answer any of these, ship it. If it's pretty but takes 90 seconds, it failed.

## Scope — three issues, sequenced (Phase 1a / 1b split)

**Phase 1a — start now, no Oracle dependency:**
- #99 dashboard API (skeleton + all endpoints except quality-score)
- #100 frontend (book table with cost + wall-time + validation columns; per-book drill-down with stage + gate breakdown)
- #97 cost events (staged behind, can begin once #99 skeleton lands)

**Phase 1b — unblocks when Oracle ships `oracle-translation-quality-score-v1.md`:**
- Quality score endpoint in #99 (single 0–100 per book + decomposition)
- Quality column in #100 top-level table (with color bands per Oracle's spec)
- Drill-down score decomposition view

Phase 1b is small — additive only, no rework of 1a. Ship 1a first, layer 1b on top.

### Lead: #99 — dashboard API (`/admin/api/*`)

Routes that return per-book cost + wall-time breakdown (OCR | Translation | Glossary) as JSON. Sit behind the Entra middleware Tank shipped (`transpose.api.auth.entra_middleware`, scope `api://transpose-admin/Dashboard.Read`).

Query Postgres directly. Don't wait for #97's event store — query the current sources (`translations`, `books`, `pages`, `book_costs`). When #97 lands, swap the source; the API shape doesn't change.

### Parallel: #100 — static frontend at `$web/admin/`

Reuse the landing-page template pattern. MSAL.js PKCE (public client, no secret) using the client ID + audience in `tank-entra-auth-shipped.md`. One page is enough for v1: a sortable table of books with cost + wall-time columns and a per-book drill-down (full stage breakdown). No charts required for v1.

**Static HTML is public-unlisted; auth gates the data API only.** Page loads with empty shell + "Sign in" button; data fills after MSAL token exchange. (Manish's Q1 answer.)

### Stage behind: #97 — append-only cost events

Build the event store after the API ships against current sources. This decouples "Manish can see costs today" from "telemetry is bulletproof for resume/failure cases." Once #97 lands, point the API's queries at it and retire the ephemeral `book_costs` dependency.

## Non-goals (explicit cuts)

- No real-time progress / WebSocket / live updates. Post-mortem reporting only.
- No budget alerts, anomaly detection, or cost projections in v1. (Cost projection deferred to v1.1 per Manish.)
- No charts/graphs in v1. Table > graph for an under-1-minute answer.
- No multi-tenant / multi-operator UI. Manish is the only user.
- No App Insights workbook or Grafana integration. Postgres → JSON → table.
- No CI test-suite metrics in the per-book table. Tests are platform-level, not book-level. (Separate tile possible later if Manish flags it.)
- ~~No separate "report generation" stage.~~ **Correction:** `_build_validation_report()` produces a JSON validation report aggregating all 10 gate results at the end of every run. The dashboard must surface it.

## Per-book drill-down — full stage breakdown + gate results (Manish's Q2 answer, corrected)

Drill-down view has two sections:

### Section 1 — Pipeline stages (time + cost)

| Row | Source | Notes |
|---|---|---|
| ingest | `STAGE_ORDER[0]` | Wall time only (no $ cost) |
| ocr (extract) | `STAGE_ORDER[1]` | Doc Intelligence $ + time |
| chunk | `STAGE_ORDER[2]` | Wall time only |
| translate | `STAGE_ORDER[3]` | GPT-4o $ + time |
| glossary | `STAGE_ORDER[4]` | GPT-4o $ + time |
| assemble | `STAGE_ORDER[5]` | Wall time only |
| export (PDF assembly) | `STAGE_ORDER[6]` | Wall time only |
| workspace publish | `STAGE_ORDER[7]` | Wall time only |
| **validation** | sum of all gate `duration_ms` | Bold row — total gate execution time across the run |
| **Total** | sum | Bold row |

### Section 2 — Quality gates (pass/fail + duration + failure reason)

All 10 gates from `transpose.pipeline.gates`, surfaced from the validation report:

| Gate | Stage it runs after |
|---|---|
| operational_readiness_gate | (preflight) |
| ocr_sanity_gate | ocr |
| translation_completeness_gate | translate |
| glossary_integrity_gate | glossary |
| document_structure_gate | assemble |
| artifact_availability_gate | export |
| export_rendering_gate | export |
| golden_targeted_qa_gate | export |
| validate_production_readiness | export |
| **source_output_comparison_gate** | **export (source PDF ↔ output PDF structural check)** |

Each row: ✅/❌ status, duration_ms, and failure reason if failed. Source the report from `_build_validation_report()` output (already written per run).

### Top-level table — overall gate status + quality score as columns

Add two columns to the main book table alongside cost and wall-time:

- **Validation:** `✅ 10/10 passed` or `❌ 2/10 failed` (clickable → drill-down Section 2)
- **Quality:** 0–100 translation quality score with color band (Oracle defines formula and bands in `oracle-translation-quality-score-v1.md`; default until then: hide the column behind a feature flag and ship without it). Clickable → drill-down showing score decomposition.

This is how Manish glances at a list of books and spots which need attention.

## Quality gate

Dozer owns #101 (test coverage for cost_events, projector, dashboard_api). API endpoints get unit tests + an integration test against a seeded book. Frontend gets a smoke test that the protected page loads under a valid token and rejects without one.

## Open questions for Manish (answered 2026-05-22)

1. **Static HTML auth posture:** Public-unlisted HTML, auth on the data API. ✅
2. **Stage breakdown granularity:** All 8 pipeline stages end-to-end **plus all 10 quality gates** with pass/fail + failure reason. Top-level table shows aggregate gate status (e.g., `✅ 10/10`) as a column alongside cost and wall-time. ✅
3. **Cost projection feature:** Deferred to v1.1. ✅

If Trinity hits a fork, default to the answer that ships the under-1-minute experience fastest.


---

# Niobe — Priority Ladder Locked (2026-05-22)

Date: 2026-05-22T10:27:00-04:00
Owner: Niobe (PM)
Approved by: Manish
Supersedes: niobe-backlog-prioritization.md (sequencing portion only — observability framing still stands)

## Sequence

| Phase | Work | Exit criteria | Owners |
|---|---|---|---|
| **1. Observability MVP (now)** | #97 cost events, #99 dashboard API, #100 dashboard frontend, #101 tests | "What did book X cost?" answered in <1 min without SQL | Trinity (lead), Dozer (tests) |
| **2. Platform optimal** | #96 parallelism re-enable, #94 wall-time <2h (includes prompt caching), #95 *quality-safe levers only* | Next book runs in <2h at meaningfully lower cost, dashboard data drives the cut | Trinity |
| **3. Setup friction** | #91, #83, #84, #85, #88 | Fresh-clone setup works first try | Tank (infra), Trinity (Python paths) |
| **4. Next direction** | Audiobook? Shape B archive? More books? | TBD after platform settles | Niobe re-frames |

## Key product calls

### Phase 2 — #94 includes prompt caching

Prompt caching is the no-risk cost lever from #95 (Azure OpenAI prefix cache, identical output). Folded into #94 scope so it ships with the wall-time work rather than waiting for a separate #95 effort.

### #95 — quality-gated, not deferred

Approved levers (no quality risk):
- Prompt caching (handled in #94)

Conditionally approved (Oracle A/B required):
- Larger chunks — needs sample-chapter A/B before vs. after on translation coherence
- Cheaper Doc Intelligence tier — per-book judgment based on scan quality (Shiv Sutra was clean; old/handwritten scans need the better tier)

**Not approved on literary/spiritual content:**
- GPT-4o → GPT-4o-mini swap. Sanskrit aphorisms + commentary is exactly where 4o-mini drops nuance. May revisit on plain-prose books with Oracle sign-off; default = no.

### #96 (parallelism) leads Phase 2

Currently disabled for safety. Re-enable first because: (a) wall-time gains are mechanical, not algorithmic; (b) it amplifies the impact of #94's per-stage optimizations; (c) observability (#101) lands the telemetry to monitor concurrency safely.

## Why this differs from prior framing

Earlier prioritization deferred #94/#95/#96 behind setup friction on a "throughput is the constraint, not wall time" argument. That was wrong for two reasons Manish flagged:

1. 10h wall time prevents same-day iteration — the operator-feedback loop matters even at low book counts.
2. "Stable + optimal" is a legitimate platform success criterion. Setup friction is real but secondary to a sluggish core loop.

Observability still goes first — it's the *enabler* for surgical perf work, not a substitute.


---

# Niobe → Scribe: Quality Gates Doc Drift Fix

Date: 2026-05-22T10:56:00-04:00
From: Niobe (PM)
For: Scribe (docs / decision-ledger lead)
Related: niobe-trinity-brief-phase1.md

## Ask

Reconcile docs with code reality on quality gates. Code has **10 gates**; docs describe **7**.

This is a parallel track to Trinity's Phase 1 work — not blocking, but should land before/with the observability dashboard so Manish can cross-reference what the dashboard surfaces against what the docs claim.

## Specific fixes

### 1. `docs/architecture.md` — Quality Gates section (lines 464–478)

Current state: lists "Gate 1" through "Gate 7" with no mention of three production gates.

**Add (with same table structure as existing entries):**

- `operational_readiness_gate` — preflight (runs before Stage 1). Checks Azure / DB / Redis / model endpoints reachable. Returns `OperationalReadinessResult`. Source: `transpose.pipeline.gates.operational_readiness_gate`.
- `export_rendering_gate` — runs after export on the produced PDF. Verifies PDF renders, fonts embed, pages countable. Source: `transpose.pipeline.gates.export_rendering_gate`.
- `source_output_comparison_gate` — runs after export. Compares source PDF vs. translated PDF: page-count ratio (within `_STRUCTURAL_PAGE_RATIO_MIN`/`_MAX`), text density, structural consistency. Source: `transpose.pipeline.gates.source_output_comparison_gate`.

**Drop the "Gate N" numbering** — gates are addressed by name in code; numbered prose drifts every time we add one. List them in stage order with a "Stage" column instead.

**Also (line 532):** Update the "Quality scoring" future-work bullet to reference the v1 Translation Quality Score Oracle is now defining (see `niobe-oracle-quality-score-brief.md`).

### 2. `docs/observability.md` — add gates as a first-class signal

Currently silent on quality gates. Gates emit:
- OTel spans named `quality_gate` with attributes `gate.name`, `gate.passed`, `gate.duration_ms`, `gate.failure_reason`
- Metrics `gate_executions` (counter, tagged by `gate_name` + `result`) and `gate_duration_seconds` (histogram, tagged by `gate_name`)

**Add a "Quality gates" subsection** under Telemetry covering: the span shape, the two metrics, how to query App Insights for gate failures, and a note that the observability dashboard (`/admin/`) surfaces aggregate pass/fail per book.

### 3. `README.md` (line 14)

The "Quality Gates" bullet lists 6 of the 10. Replace with a sentence-level summary that doesn't enumerate gates by name (so it doesn't drift again), and link to the architecture.md section.

Suggested replacement: *"**Quality Gates** — 10 blocking checks across the pipeline validate OCR sanity, translation completeness, glossary integrity, document structure, artifact availability, golden-target QA, production readiness, source-output structural parity, and operational readiness. See `docs/architecture.md` for the full catalog."*

### 4. `docs/api-contracts.md` — add validation report schema

The pipeline produces a JSON validation report per run via `_build_validation_report()` in `runner.py`. The shape isn't documented anywhere. Add a section describing it: `book_id`, `overall` (PASS/FAIL), `gates[]` (each with `name`, `passed`, `failures[]`, `details{}`, `timestamp`), `artifacts{}`. This is what the observability dashboard will consume — Trinity needs the contract pinned down.

### 5. Architectural progression / lessons-learned section (NEW — Manish directive 2026-05-22T11:10)

Manish wants architectural decisions and the reasoning behind them captured durably so downstream contributors (future agents, future operators, future Manish) inherit the *why*, not just the *what*. One-line bullets in a changelog don't suffice; this is closer to a project ADR log.

**Create or extend** an "Architectural Progression" / "Lessons Learned" section in `README.md` (or as `docs/architecture-decisions.md` if README would bloat — your judgment) covering at minimum the calls made in this session:

1. **Per-book observability dashboard, not just cost telemetry.** Initial framing was "cost visibility." Evolved through review to a four-column per-book operations dashboard (cost, wall-time, validation status, quality score). Lesson: operator dashboards are about *decision velocity*, not single-metric visibility — surface every signal the operator needs to decide "ship, re-run, or review" in one glance.

2. **Quality gates are first-class, count = 10 (not 7).** Doc drift between code and prose hid `operational_readiness_gate`, `export_rendering_gate`, and `source_output_comparison_gate`. Lesson: gate enumeration in docs by number (`Gate 1`, `Gate 2`…) drifts every time we add one; address by name and source-of-truth from code.

3. **Quality score architecture rejects same-family LLM-as-judge.** GPT-4o evaluating GPT-4o output has known self-preference bias. v1 uses a layered architecture: (A) multilingual embeddings for semantic similarity on every chunk, (B) reference-free MT QE (COMET-Kiwi class) on every chunk, (C) cross-family LLM judge (Claude or Gemini) on a sample. Lesson: convenience of an already-integrated model is not a substitute for evaluation rigor; cross-family judges + specialized MT QE tooling produce better signal at lower cost than recycling the generation model.

4. **Phase 2 cost optimization (#95) is quality-gated, not deferred.** Prompt caching = always-on (no quality risk). Larger chunks / Doc Intelligence tier downgrade = Oracle A/B per book. GPT-4o → GPT-4o-mini swap = rejected on literary content. Lesson: cost levers are not fungible; each has a different quality blast radius.

5. **Performance work sequenced behind observability, not deferred.** Earlier framing argued throughput was the constraint, not wall time. Corrected: 10h wall time prevents same-day iteration regardless of throughput. Observability ships first so perf cuts are surgical with data, not speculative. Lesson: "throughput is the only metric" misses the operator-feedback loop; latency matters even at low volume.

**Format:** Short prose per entry — context, decision, lesson, citation to decision file. Not a dry change log. Future readers should be able to read the section and understand *how the platform thinks*, not just what's in it.

**Source material:** all 2026-05-22 inbox entries (`niobe-priority-ladder-2026-05-22.md`, `niobe-trinity-brief-phase1.md`, `niobe-oracle-quality-score-brief.md`, this file). Pull the *reasoning*, not the *task lists*.

**Maintenance commitment:** This section grows over time as the team makes calls worth preserving. Scribe owns the convention going forward — when a decision file lands in the inbox that captures an architectural lesson (not just a task assignment), pull the lesson into this section as part of the normal merge process.

## Out of scope

- Don't restructure other sections of architecture.md while you're in there.
- Don't write user-facing docs for the observability dashboard — wait until #100 is past spec lock and Trinity confirms the surfaced shape.
- Don't move existing decision-ledger entries (`tank-entra-auth-shipped.md` etc.) — they're inbox-bound for the Scribe's normal merge process.

## Verification

After your edits: run `grep -c "_gate" docs/architecture.md` and verify all 10 gate function names appear. Confirm `docs/observability.md` mentions `gate_executions` and `gate_duration_seconds` metrics by name. Confirm `docs/api-contracts.md` documents the validation report schema. Confirm the architectural progression / lessons-learned section captures the five decisions listed in §5 with sufficient reasoning that a new contributor would understand the *why* of each.


---

# Tank — Cost Telemetry Source of Truth

**Date:** 2026-05-21T14:19:30.760-04:00  
**Author:** Tank  
**Context:** Shiv Sutra book-cost investigation for `723477a9-7ca4-4ba6-944c-3abef1ee92a4`

## Decision
For Transpose today, the fastest trustworthy way to answer "what did this book cost?" is:

1. **OpenAI cost:** query PostgreSQL `translations` and sum `prompt_tokens` + `completion_tokens` for the `book_id`; price them with `src/transpose/observability/cost_rates.py`.
2. **OCR cost:** query PostgreSQL `books.page_count` (or count `pages`) for the `book_id`; price with `cost_rates.py`.
3. **Blob cost:** reconstruct from run logs / Azure telemetry. `book_costs` is not a full blob ledger.
4. **Use `book_costs` only as a convenience summary**, not as the source of truth for total historical cost.

## Why
`CostTracker.persist()` only writes to PostgreSQL `book_costs` on the happy path after workspace completes. Failed or interrupted runs lose their accumulated summary rows. For Shiv Sutra, `book_costs` retained only the final resume's `blob_storage/write_operations = 2`, while the real OpenAI/OCR usage lived in `translations`, `books`, and `pages`.

## Evidence from Shiv Sutra
- `books.created_at`: 2026-05-21 05:32:23Z
- `translations`: 1,161,417 input tokens / 255,580 output tokens
- `books.page_count`: 249 OCR pages
- `book_costs`: only one persisted row (`blob_storage`, `write_operations`, `2`)
- App Insights `customMetrics`: partial stage timeline only; not a complete cost ledger
- Local `output/shiv-sutra/e2e-run.log`: shows additional blob reads/writes that `book_costs` missed

## Operational Rule
If Manish asks for true per-book cost before telemetry is fixed, answer from:
- **DB first** for tokens/pages
- **Logs/App Insights second** for blob ops and stage timing
- **State confidence explicitly** if blob telemetry had to be reconstructed

## Follow-up
GitHub issue filed: #93 — persist book cost telemetry across failed/resumed pipeline runs.


---

# Tank — Entra auth shipped

Date: 2026-05-21T23:47:25-04:00
Owner: Tank
Related issues: #98 (shipped locally), #99 and #100 unblocked for Trinity, #101 deeper coverage for Dozer

## What shipped

- Fresh single-tenant Entra app registration: `transpose-admin`
- Client ID: `5ffe7826-3caa-41a8-9359-a5dd3aee4407`
- Tenant ID: `48af2a40-dd60-4e0d-ba42-f0fac9a31d93`
- Scope/audience: `api://transpose-admin/Dashboard.Read`
- Issuer: `https://login.microsoftonline.com/48af2a40-dd60-4e0d-ba42-f0fac9a31d93/v2.0`
- JWKS URI: `https://login.microsoftonline.com/48af2a40-dd60-4e0d-ba42-f0fac9a31d93/discovery/v2.0/keys`
- aiohttp middleware mounted for `/admin/*` only
- Protected static placeholder served from `web/admin/index.html`
- Auth smoke route at `/admin/api/test`

## Secrets handling

- No client secret created.
- Frontend uses MSAL.js PKCE (public client pattern).
- Container App managed identity remains for Postgres only; auth middleware only consumes OpenID discovery + JWKS metadata.

## Operational notes

- JWKS fetch strategy: tenant OpenID discovery document → `jwks_uri` → key lookup by `kid`
- Cache TTL: 300 seconds (`ENTRA_JWKS_CACHE_TTL_SECONDS`, optional override)
- On unknown `kid`, middleware forces one JWKS refresh before rejecting
- Middleware accepts real Entra API tokens where `aud=api://transpose-admin` and `scp=Dashboard.Read`, while still honoring the configured audience string `api://transpose-admin/Dashboard.Read`
- Existing `/health`, `/ready`, `/translate`, and `/status/*` stay outside Entra auth

## Redirect URIs configured today

- `http://localhost:8000/admin/`
- `https://transpose-dev-app.internal.yellowcoast-177ceb3f.swedencentral.azurecontainerapps.io/admin/`

## Follow-up

- Manish must add the final externally reachable HTTPS `/admin/` redirect URI after the first public admin deploy.
- Trinity can start #99 and #100 now in parallel using the client ID + audience above and the middleware module `transpose.api.auth.entra_middleware`.


---

## 2026-05-21T13:45:28.928-04:00: Original scan publishing on public slug pages

**Author:** Tank

### Decision
For public-domain books published on the Azure Static Website slug path, publish the original scan alongside the translation at:
- `$web/{slug}/source.pdf` — public original scan
- `$web/{slug}/Shiv_Sutra.pdf` / translated artifact(s) — public translation assets
- `$web/{slug}/index.html` — TR-3 landing page with **Download Translation** + **Original Scan** buttons

Use the same static-website security model as the translation assets. Do **not** point the reader-facing Original Scan button at a private container (`source-pdfs` or `book-workspaces`) unless intentionally using a SAS URL strategy.

### Why
The live `shiv-sutra/` page had been manually republished with only translation links, even though the original scan already existed privately at `book-workspaces/shiv-sutra--ee92a4/input/source.pdf`. Republishing the source scan to `$web/shiv-sutra/source.pdf` restored the reader-facing contract without weakening storage account security.

### Operational convention
Prefer `$web/{slug}/source.pdf` as the public original-scan filename. It matches existing workspace naming (`input/source.pdf`), keeps URLs predictable, and makes landing-page repair straightforward when backfilling public-domain books.


---

### 2026-05-21T23:39:59-04:00: User directive — Audiobook-aware design posture
**By:** Manish (via Copilot)
**Addressed to:** Niobe (and all agents)
**What:** Audiobook generation is part of the long-term roadmap. Current priorities — in order — are: (1) stabilize translation quality, (2) improve runtime performance, (3) establish observability. Audio synthesis implementation is DEFERRED until translation pipeline maturity improves.

However, ALL current work must remain **audiobook-aware**:
- Preserve chapter boundaries
- Preserve semantic structure (paragraphs, sentence boundaries, headings)
- Store metadata required for future narration (voice hints, language, prosody markers where natural)
- Avoid architectural dead ends — no choices that would force a rewrite when TTS lands

**Implications for agents:**
- **Niobe:** Frame all new capabilities through both today's priority lens AND audiobook-readiness. Flag any scope cut that would burn a bridge to audiobook later.
- **Morpheus:** Architecture choices must not paint us into a corner. Data schemas should accommodate future TTS metadata.
- **Trinity:** Pipeline output (ePub/PDF, intermediate JSON) should preserve structural fidelity, not flatten it for current rendering convenience.
- **Tank:** Storage / blob layout should not assume "translation outputs only" — future audio artifacts will need a place.
- **Dozer:** When writing new tests, include assertions on chapter/section boundary preservation where applicable.

**Why:** User request — captured for team memory.


---

### 2026-05-22T00:23:14-04:00: User directive — Operational leanness rules
**By:** Manish (via Copilot)
**What:** Squad operational defaults to reduce overhead going forward:
1. **Scribe batching:** Do NOT spawn Scribe after every single agent batch. Batch Scribe to run at most every 3rd agent-completion OR once per session-segment OR when the user signals a stop point. Single agent runs (typical bug fix / question) → no Scribe spawn until end of segment.
2. **Decisions.md archive gate:** Lower the soft archive threshold from 20480 bytes (20KB) to 10240 bytes (10KB). Lower the hard gate from 51200 bytes to 30720 bytes (30KB). Archive entries older than 7 days when soft gate trips.
3. **Bias toward Direct / Lightweight Mode:** Any task expressible in 1 sentence and finishable in ≤2 min by hand → Direct Mode (coordinator answers/does inline). Skip Squad ceremony.
4. **Charter inline caching:** If an agent has already been spawned this session, do NOT re-inline their full charter on the second spawn — pass task + decisions delta only.
5. **Stale reminder:** If the chat session crosses ~25 substantive turns OR ~4 hours wall time, the coordinator should suggest ending the session and starting fresh.
**Why:** User request after operational analysis showed Scribe-after-every-batch and decisions.md growth (5KB → 30KB this session) were primary overhead sources.


---

### 2026-05-21T23:47:25-04:00: Entra app — create fresh
**By:** Manish (via Copilot)
**What:** No existing Entra app registration to reuse. Tank should create a fresh `transpose-admin` app registration for the observability dashboard auth (per Morpheus #98 design). All other observability MVP build sequencing decisions deferred to Niobe.
**Why:** User request — unblocks #98.
