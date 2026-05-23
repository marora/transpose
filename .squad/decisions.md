# Transpose Decisions Log

Decisions recorded for team memory and cross-agent context.

**Current archive state:** Entries from 2026-05-21 design specs through 2026-05-22 morning have been archived to `.squad/decisions-archive.md` (231KB) to keep this log under 51KB. See archive for Oracle Quality Score spec, Phase 1 brief, architecture decisions, cost telemetry design, and lessons-section source. Current entries: directives, Trinity Phase 1a completion, and latest work items.

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
# Trinity — Phase 1a shipped: dashboard API + frontend (issues #99, #100)

Date: 2026-05-22T15:40:25Z
Owner: Trinity
Related: niobe-trinity-brief-phase1.md, tank-entra-auth-shipped.md, niobe-oracle-quality-score-brief.md

## What shipped (Phase 1a)

**Issue #99 — Dashboard API (`/admin/api/*`)**
- New module: `src/transpose/api/dashboard.py` with `register_dashboard_routes(app)`.
- `GET /admin/api/books` — list with summary columns (cost / wall-time / validation / quality-stub).
- `GET /admin/api/books/{book_id}` — full detail: 8 pipeline stages + validation row + total row, plus all 10 quality gates (pass/fail + duration_ms + failure reason).
- Sits behind Tank's `entra_admin_middleware` automatically (any `/admin/*` path is auth-gated).
- Reads directly from Postgres (`books`, `book_costs`, new `book_validation_reports`). API shape is forward-compatible with #97 (`cost_events`) — only the data source swaps.

**Issue #100 — Static frontend (`web/admin/`)**
- `index.html` / `app.js` / `style.css`. Public-unlisted shell; data API enforces auth.
- MSAL.js PKCE (public client) using Tank's tenant + client ID + scope.
- Sortable book table with Cost / Wall-time / Validation columns. Drill-down panel shows full stage breakdown + all 10 gates.
- Quality column hidden behind a feature flag (`document.body.quality-on`) until Oracle's spec lands — additive only, no rework needed for Phase 1b.

**Supporting infra**
- New Alembic migration `3a9e1b27c4f1_add_book_validation_reports.py` — append-only `book_validation_reports` table (book_id, overall, report JSONB, created_at). Indexed on (book_id, created_at DESC).
- `Database.ensure_validation_reports_table()`, `save_validation_report()`, `get_latest_validation_report()` helpers.
- `runner.py` now persists the validation report to Postgres at every terminal branch (success + both error paths) — best-effort, never blocks the pipeline.
- `GateResult.duration_ms` field stamped by `_run_gate()` so the dashboard can surface per-gate timing without scraping OTel.

**Tests**
- `tests/unit/api/test_dashboard.py` — 12 passing tests covering helpers (`_rollup_costs`, `_summarize_gates`, `_validation_summary_label`, `_wall_time_seconds`) and endpoint behaviour with a fake DB + Tank's auth path.

## Known Phase 1a fidelity gaps (closed by #97)

These are explicit, documented in API responses, and surface in the UI as inline notes:

1. **Per-stage wall-time is `null`** for every stage except `total` (book.updated_at - book.created_at) and `validation` (sum of gate durations). #97's `cost_events` table will give us stage-level wall time.
2. **OpenAI spend rolls under `translate`** — `book_costs` has no stage tag, so glossary's GPT-4o spend can't be separated from translation's. Glossary shows `cost_usd: 0` with a note. Fixed by #97.
3. **Blob storage spend is attributed to `export`** — a heuristic. Workspace publish writes blobs too; this will get more accurate with #97.

The API response shape includes a per-stage `note` field for exactly this. When #97 lands, swap the data source in `_rollup_costs()` / add per-stage wall-time — no contract changes.

## Phase 1b status

Quality score endpoint + column is staged behind Oracle's `oracle-translation-quality-score-v1.md`. Current state: every `/admin/api/books*` response includes a `quality: {available: false, reason: "Awaiting Oracle's translation quality score spec…", score: null, band: null}` stub. The frontend hides the column until at least one book reports `available: true`. When Oracle ships:

- Implement scoring in a new helper (e.g., `transpose.api.dashboard_quality`).
- Replace `_quality_stub()` with the real call; same response shape.
- Drill-down's "Translation quality" section already renders score + band when available.

No changes needed in #100 to support this — the column appears automatically.

## Coordination

- **Dozer:** #101 test coverage scope — please add an integration test that seeds a book, runs the pipeline (or stubs `_build_validation_report` output), and asserts the dashboard endpoint surfaces gate results from DB. Unit coverage is in `tests/unit/api/test_dashboard.py`. Smoke test for the static page (rejects without token, loads with one) is partially covered by `test_entra_middleware.py`.
- **Niobe:** Phase 1a outcome target is met for runs that complete with the new runner. Existing pre-migration books will show "—" for validation until they re-run (no historical report persisted). If you want a backfill of Shiv Sutra etc., flag it and I'll do a one-off insert of their on-disk `validation-report.json` files into the new table.
- **Tank:** No changes needed on your side. The Entra middleware automatically protects `/admin/api/books*` because they live under `/admin/*`. Audience/scope unchanged.

## Validation

- `ruff check` clean on all new files (one pre-existing E501 in `database.py:369` not from this work).
- `pytest tests/unit/api/test_dashboard.py` — 12/12 passing.
- `pytest tests/unit/api/ tests/unit/pipeline/test_resume_from.py` — 51/52 passing; the one failure (`test_non_admin_routes_remain_unaffected`) is pre-existing on master HEAD (`Settings.get_entra_authority_url` missing — unrelated to this work).

## Files changed

```
A  migrations/versions/3a9e1b27c4f1_add_book_validation_reports.py
A  src/transpose/api/dashboard.py
A  tests/unit/api/test_dashboard.py
M  src/transpose/api/__init__.py             (register_dashboard_routes call)
M  src/transpose/pipeline/runner.py          (persist validation report, surface duration_ms)
M  src/transpose/pipeline/gates.py           (GateResult.duration_ms field)
M  src/transpose/services/database.py        (validation report helpers)
M  web/admin/index.html                      (full dashboard shell)
A  web/admin/app.js                          (MSAL PKCE + table + drill-down)
A  web/admin/style.css                       (minimal, scannable)
```
### 2026-05-22T16:01:10-04:00: User directive
**By:** Manish (via Copilot)
**What:** "run 3 is not as important, let's take care of all of these items first" — referring to Niobe's 8-gap readiness assessment (Oracle Score wiring, cost guardrails, per-book cost events #97, README lessons revamp, docs/auth.md posture, uncommitted real code, Phase 1b quality column, prime-time bridge work). Deprioritize triggering e2e run #3 until those gaps close.
**Why:** Scope decision — capture for team memory.
# Niobe: Gap Closure Plan — Prime Time Prep
**Filed by:** Niobe  
**Timestamp:** 2026-05-22T16:01:10-04:00  
**Requested by:** Manish  
**Trigger:** Manish directive — "run 3 is not as important, let's take care of all of these items first"

---

## Issue Filing Summary

| # | Title | Owner | Wave |
|---|---|---|---|
| #103 | infra(oracle-score-layer-a): provision LaBSE sidecar for Container App | Tank | Wave 2 |
| #104 | feat(oracle-score-layer-c): wire Anthropic Sonnet 4.5 judge into pipeline | Trinity | Wave 2 |
| #105 | infra(cost): set minReplicas=0 in container-app.bicep + provision $25/mo RG budget alert | Tank | Wave 1 |
| #106 | chore(repo): commit drifted real code — azure_rbac_retry, workspace/, backfill_workspace.py + tests | Trinity | Wave 1 |
| #107 | docs(auth): commit docs/auth.md — posture decision required | Scribe | Wave 2 |
| #108 | docs(readme): commit lessons revamp + add public-lessons-curation skill | Scribe | Wave 1 |
| #109 | feat(dashboard): Phase 1b quality column — render Oracle quality scores in admin dashboard | Trinity | Wave 3 |

---

## Sequenced Execution Plan

### Wave 1 — Ship immediately, no dependencies (parallel)

All three items are independent. They can land simultaneously.

**#105 — Cost guardrails (Tank, 0.5 day)**
- Change `infra/modules/container-app.bicep:53` from `minReplicas = 1` → `minReplicas = 0`
- Provision $25/month RG budget alert on `transpose-dev` Resource Group
- Document teardown commands in `infra/README.md`
- Money is leaking today. Highest urgency in Wave 1.
- Coordinate with #102 (Foundry dormant) — can be in the same PR if Tank prefers.

**#106 — Drifted code commit (Trinity, 0.5–1 day)**
- PR 1: `azure_rbac_retry.py`, `workspace/`, `backfill_workspace.py`, tests
- PR 2 (separate): CI/squad infra (`.github/workflows/squad-*.yml`, `.copilot/skills/`, `pyproject.toml`, `uv.lock`, `.env.example`)
- Purely mechanical — files exist, tests pass. No decisions required.
- Do NOT include `docs/auth.md` (that is gated on Manish decision → #107).

**#108 — README lessons revamp + public-lessons-curation skill (Scribe, 2h)**
- Gate lifted by Manish: ship BEFORE run #3, not after.
- Source: `niobe-lessons-revamp-2026-05-22` packet in `.squad/decisions.md`
- Delivers: 11-lesson README rewrite + `.squad/skills/public-lessons-curation/SKILL.md`

**Open question for Manish (Wave 1 blocker for #107):**
`docs/auth.md` posture — pick one:
- **(a)** Commit as-is (PKCE = no secret; tenant/client IDs are public values)
- **(b)** Commit as template (replace real IDs with `${ENTRA_TENANT_ID}` placeholders)
- **(c)** Gitignore it (keep local-only, archive content in decisions.md)

Once Manish decides, Scribe executes #107 in 30 minutes.

---

### Wave 2 — Wait on Wave 1, then ship (can overlap)

Wave 2 begins as soon as Wave 1 Tank work clears (#105 merged). Trinity and Tank can work in parallel.

**#103 — Oracle Layer A sidecar (Tank, 1–2 days)**
- LaBSE sidecar on Container App (4 GiB, weights baked in, no SKU upgrade)
- docker-compose stub for local dev (Trinity dependency for #104 full integration)
- Kicks off as soon as Wave 1 is clear.

**#104 — Oracle Layer C client (Trinity, 1–2 days)**
- Anthropic Sonnet 4.5 judge, post-export, non-blocking
- Pulls API key from Key Vault (coordinate key name with Tank)
- Can develop against a stub LaBSE endpoint — does NOT need #103 deployed first
- Start in parallel with #103 immediately.

**#107 — docs/auth.md commit (Scribe, 30 min)**
- Executes as soon as Manish picks posture (a/b/c)
- Not dependent on any technical work

---

### Wave 3 — Depends on Wave 2

**#109 — Phase 1b dashboard quality column (Trinity, 1 day)**
- Depends on #104 (Layer C wiring) being merged
- Completes the operability triangle: cost + wall-time + quality on one page
- Does not need #103 (LaBSE sidecar) for initial render; Layer A composite can be added when sidecar lands

---

### Run #3 — Re-evaluate after Wave 2 ships

With Manish's directive to close gaps first, run #3 is deferred until Wave 2 is in place. At that point:
- Run #3 becomes a **true "validate against real book"** run, not a platform validation run
- The Oracle quality score will fire post-export and populate the Phase 1b dashboard
- The cost guardrails will be in place, so idle cost doesn't bleed during the run
- The drifted code will be committed, so the working tree is clean

**This is the right sequencing.** Run #3 on a fully-wired platform is more valuable than run #3 as a dev checkpoint.

---

### Out of Scope — Already filed, separate backlog

The following are tracked and NOT blocked by this gap-closure push. They belong in the standing backlog and should be picked up at natural breakpoints:

| Issue | Title | Note |
|---|---|---|
| #94 | Performance <2h wall time | After #97 (cost events) gives us per-stage timing data |
| #95 | Cost <$5/book | After dashboard + quality score are in place |
| #96 | Parallelism defaults | After #97 cost events confirm baseline |
| #97 | Per-book cost events | Trinity, Step 3 — pick up alongside Wave 2 if bandwidth allows (cheap with dashboard already wired) |
| #78/#79 | Translation quality (pre-Oracle) | Superseded by Oracle v1 spec; close or defer |
| #85/#88/#91/#92 | Workspace bugs, SAS validation | Some addressed by #106 commit |
| #98 | Entra infra | Coordinate with #107 posture decision |
| #99/#100/#101 | Phase 1a dashboard | Already shipped — close if resolved |
| #102 | Foundry dormant cost | Can fold into #105 (same Tank PR, same cycle) |

**Cheap alongside pick:** #97 (per-book cost events) and #102 (Foundry dormant) are cheap if Tank and Trinity have bandwidth during Wave 2. #97 especially — the dashboard is wired, it's just adding event emission to the pipeline.

---

## Open Questions for Manish (max 3)

### Q1 — `docs/auth.md` posture [BLOCKING #107]
Pick: **(a)** commit as-is, **(b)** commit as template, **(c)** gitignore.
Scribe executes in 30 minutes once you decide.

### Q2 — Should @copilot pick up the mechanical chore PRs?
Issue #106 (drifted code commit) is largely mechanical — files exist, tests pass. If Trinity's queue is full, `@copilot` can open both PRs (src + CI/infra) with zero design decisions required. This is an appropriate fit for Copilot: pure commit-and-push work, not architectural reasoning.

### Q3 — Wave 3 gate: wait for run #3 or ship immediately after Wave 2?
Option A: Ship #109 (Phase 1b quality column) immediately after #104 merges.
Option B: Wait for run #3 to produce real Oracle score data first, then ship #109 with real data to validate against.

**Recommendation:** Option A. The dashboard render is testable with stubbed data. Real-book validation is for QA, not a gate. Keep momentum.

---

## Total Estimate

| Wave | Duration | Critical Path |
|---|---|---|
| Wave 1 | 1–2 days (parallel) | #105 (0.5d), #106 (1d), #108 (2h) |
| Wave 2 | 2–3 days (parallel) | #103 + #104 in parallel (1–2d each) |
| Wave 3 | 1 day | #109 after #104 |
| **Total to prime time** | **4–6 days from today** | Run #3 validates after Wave 2 |

---

*Plan synthesized from: readiness assessment (niobe-readiness-assessment-2026-05-22.md), GitHub issue audit, Manish directive 2026-05-22. No agents spawned.*
# Niobe: Platform Readiness Assessment — 2026-05-22

**Filed by:** Niobe  
**Timestamp:** 2026-05-22T15:50:33-04:00  
**Requested by:** Manish  
**Purpose:** Pre-run #3 / "prime time?" integrated status across all eight dimensions. Reference document for the team.

---

## Top-Line Summary (10-second scan)

**Run #3: GO.** Infrastructure, schema, code, and tests are aligned. The container is healthy, auth is active, all 52 tests pass.

**Prime time: NOT YET.** Four concrete gaps separate "another dev run" from "invite real users": Oracle quality score not wired, cost guardrails (Step 1.5a) not applied, the lessons revamp hasn't landed in README, and `docs/auth.md` is untracked with live credentials.

**Execution quality is solid; operational infrastructure needs one more cycle before calling this production-grade.**

---

## 1. E2E Run #3 Readiness

**Verdict: ✅ READY**

All four criteria confirmed from Tank's Step 7 deploy report (`tank-step7-deploy-DONE.md`):

- **Schema:** Alembic head = `3a9e1b27c4f1` (Step 6 DONE-IDEMPOTENT). The `book_validation_reports` table is live and append-only.
- **Container:** Revision `transpose-dev-app--0000008`, image `sha-4e2d527` / `v5`, `active: true`, `trafficWeight: 100`.
- **Health:** kube-probe `/health` = 200 OK within cold-start window; App Insights telemetry flowing; `/admin/api/books` = 401 (auth gate active, not 500).
- **Code/schema alignment:** Image built from commit `4e2d527`. HEAD is `ac1cb46` (Scribe drain — docs/squad only, no code delta). Deployed image matches the code the schema was designed for. ✅

**One active gotcha (flagged by decisions.md):** The first production write of `_persist_validation_report` could expose a DB schema/permissions mismatch. The helper is best-effort — it won't abort the run — but the Phase 1a dashboard would stay empty for run #3 if the write fails silently. Not a blocker; watch the cold-start logs during run #3 for any `Failed to persist validation report` warnings (Tank confirmed none appeared in the 80-line cold-start sample).

**Rollback path confirmed:** `transpose-dev-app--rb2-7397468` (`v4`) is the prior revision. No DB rollback needed — schema is additive and backward-compatible.

---

## 2. Performance — Optimal?

**Verdict: ⚠️ READY WITH CAVEATS**

**What's real and wired:**
- Translation concurrency: `asyncio.Semaphore(input.concurrency)` with default `concurrency=5` in `TranslateInput` dataclass (`translate.py:15,205`). Parallel mode uses `asyncio.gather` across all chunks through the semaphore. This is real, wired, and effective.
- Gate duration telemetry: `gate_duration_seconds` histogram tagged by `gate_name` is in `observability/metrics.py`; `gate.duration_ms` is persisted in validation reports. Observability gates for measuring run #3 are live.

**Known-suboptimal (not blocking):**
- OCR is structurally serial: a single cloud poller per book — Azure Document Intelligence processes the document internally, but our pipeline submits one job and polls to completion. There is no page-level fan-out on the pipeline side. On a 250-page book this dominated wall time (Shiv Sutra: ~5h 47m of a 10h 32m run). No fix is in scope for run #3.
- Translation prompt overhead: ~810k of 1.16M input tokens on Shiv Sutra were repeated scaffold (system/user framing × 454 chunks). This inflates cost without improving quality. Tracked as issue #101 (Dozer, Step 5 of the priority ladder — intentionally deferred until step #97 cost events are in place to measure it precisely).
- **Parallelism diagnosis skill** (`.squad/skills/pipeline-perf-diagnosis/`) is on disk and actionable for future runs.

**Run #3 defaults are reasonable.** We are not flying blind — duration_ms is captured per gate and per book. If run #3 surfaces a surprise, Trinity has the skill to diagnose it.

---

## 3. Cost — Optimal?

**Verdict: ⚠️ READY WITH CAVEATS**

**In scope for run #3 (nothing changed):**
- Cost structure is identical to Shiv Sutra: GPT-4o tokens + Azure Document Intelligence pages. No new cost surface has been added in the deployed revision.
- Oracle Quality Score (Anthropic API + LaBSE sidecar) is **NOT WIRED** — confirmed. It's post-export, non-blocking, not deployed. It adds zero cost to run #3.

**Gaps — not blocking run #3, but money is leaking:**
- **Step 1.5a NOT done.** `infra/modules/container-app.bicep` line 53 still reads `param minReplicas int = 1`. The $25/month RG budget alert has not been provisioned. The dormant-cost lesson is in the README and decisions.md, but the IaC fix hasn't shipped. Every idle day costs ~$4–$10 depending on Container App and Foundry Agent state.
- **Foundry Agent billing** continues at ~$8.95/day idle until Step 1.5b (IaC under `azd` lifecycle) is complete.

**Action needed (Tank, Step 1.5a, 0.5 day):** Change `minReplicas` default to `0` for non-prod in Bicep, add RG budget alert at $25/month, document `az` teardown commands in `infra/README.md`. This is independent of run #3 and should ship immediately after.

---

## 4. Stability

**Verdict: ✅ READY**

**Test suite:** All 52 tests passing as of 2026-05-22T15:50.
- `tests/unit/pipeline/test_resume_from.py` + `tests/unit/test_export_visual.py`: 48 passed in 5.21s ✅
- `tests/unit/api/test_entra_middleware.py`: 4 passed in 13.99s ✅ — including `test_non_admin_routes_remain_unaffected`. The pre-existing failure cited in the pre-commit readiness verdict is **resolved** — Trinity's Settings fix (`get_entra_authority_url`) was included in the committed code. No test is failing.

**Resume semantics:** Idempotent stage design confirmed in architecture.md. No changes to the resume path in the `4e2d527` commit. The `_persist_validation_report` call exists on all three terminal branches in `runner.py` (lines 690, 724, 758) — success, failure-after-partial-work, and clean-exit paths. Coverage is complete.

**No regressions introduced** by the Phase 1a dashboard additions (`book_validation_reports` table, `_build_validation_report`, `_persist_validation_report`). The new table is append-only; the persist helper is best-effort and wrapped to not abort the run.

---

## 5. Documentation Up to Mark?

**Verdict: ⚠️ READY WITH CAVEATS**

**What Scribe's `7397468` commit delivered (confirmed):**
- `docs/architecture.md`: 10-gate catalog by function name in stage order ✅
- `docs/observability.md`: gate spans/metrics with `gate_duration_seconds` histogram, `gate.duration_ms` per-gate field, dashboard linkage ✅
- `docs/api-contracts.md`: validation-report schema ✅
- README pipeline summary: updated ✅
- README "Architectural Progression / Lessons Learned": dormant Azure cost lesson (§1) committed ✅

**Gaps:**

1. **`docs/auth.md` — UNTRACKED, SENSITIVE.** File exists on disk (`docs/auth.md`) with live Entra tenant ID (`48af2a40-dd60-4e0d-ba42-f0fac9a31d93`), client ID (`5ffe7826-3caa-41a8-9359-a5dd3aee4407`), and redirect URIs. It has no prior squad decision trail. This file needs a decision: (a) commit it as-is (acceptable if the tenant/client IDs are non-secret by design — Entra PKCE requires no client secret, so these are public values), (b) gitignore it and keep it local-only, or (c) template it. **Owner: Tank or Manish to decide posture; Scribe to execute.** Not blocking run #3 but should not linger unresolved.

2. **README Lessons Learned revamp NOT SHIPPED.** Niobe's full 11-lesson rewrite (new grouping, 5 new entries, public-reader voice) is in decisions.md as `niobe-lessons-revamp-2026-05-22` but is explicitly held pending (a) run #3 green and (b) Manish sign-off. This is by design — execute after this assessment.

3. **`public-lessons-curation` skill NOT on disk.** The spec is authored in decisions.md (Part 4 of the revamp packet) but Scribe has not yet written it to `.squad/skills/public-lessons-curation/SKILL.md`. Executes alongside the README rewrite.

---

## 6. Lessons Learned Captured?

**Verdict: ⚠️ READY WITH CAVEATS**

**In decisions.md (merged by Scribe's drain, `ac1cb46`):**
- Observability/FinOps framing ✅
- Backlog prioritization ✅
- e2e run #3 readiness + coordinator handoff ✅
- Dormant cost lesson ✅ (also in README §1)
- Lessons revamp (30KB packet, 11 lessons, skill spec) ✅ — merged into decisions.md, **pending README commit**
- Priority ladder v2 ✅
- Oracle Translation Quality Score v1 ✅
- Parallelism diagnosis (Trinity) ✅

**Skills on disk and discoverable:**
- `.squad/skills/pipeline-perf-diagnosis/` ✅
- `.squad/skills/azure-auth-protected-dashboard/` ✅
- `.squad/skills/azure-entra-pkce-aiohttp-middleware/` ✅
- `.squad/skills/static-website-book-downloads/` ✅
- `.squad/skills/gate-real-book-calibration/` ✅
- `.squad/skills/og-landing-page-sas-blob/` ✅
- `.squad/skills/content-filter-bypass/` ✅
- `.squad/skills/pdf-qa-regression/` ✅

**Gap:** `.squad/skills/public-lessons-curation/SKILL.md` — not yet on disk. The spec is authored and waiting for Scribe to write it after run #3 green. This is the only lesson discussed in session that hasn't been recorded as a retrievable skill.

**Nothing was discussed and then lost.** All major decisions are in decisions.md.

---

## 7. GitHub Repo Up to Date?

**Verdict: ⚠️ READY WITH CAVEATS**

**Alignment confirmed:**
- HEAD `ac1cb46` = `origin/master` ✅ — fully pushed, no local-only commits.
- Scribe's last commit `ac1cb46` is pushed ✅.
- Image deployed (`sha-4e2d527` = commit `4e2d527`) predates the Scribe drain by two commits — the drain was docs/squad only, no code delta. The deployed container is consistent with the codebase. ✅

**50+ uncommitted items — what matters for run #3:**

The deployed image (`sha-4e2d527`) is what executes run #3, not the local working tree. None of the uncommitted src files affect container behavior. However, three categories need attention:

| Category | Files | Verdict |
|---|---|---|
| **Run #3 safe to ignore** | `output/`, `osho-validation-report.json`, `.vscode/`, Zone.Identifier artifacts | Local artifacts; don't commit |
| **Should be committed (next cycle, not now)** | `src/transpose/services/azure_rbac_retry.py`, `src/transpose/workspace/`, `src/transpose/pipeline/workspace.py`, `src/transpose/backfill_workspace.py`, `tests/unit/services/test_azure_rbac_retry.py`, `tests/unit/workspace/`, `tests/integration/`, `tests/unit/pipeline/test_landing_page.py`, `scripts/provision-admin-app-registration.sh`, `scripts/smoke.sh` | Real code with tests — should land in next commit cycle (Trinity/Tank own these) |
| **Decision needed before committing** | `docs/auth.md` | Contains live Entra IDs — posture decision required (see §5) |
| **Squad/CI infrastructure** | New `.github/workflows/squad-*.yml`, `.copilot/skills/` modified files, `.squad/agents/trinity/execution-brief.md`, `pyproject.toml`, `scripts/azure-setup.sh`, `.env.example`, `uv.lock` | Should go in a `chore` PR after run #3 |

**Conclusion:** Run #3 executes off the deployed image, so no uncommitted file causes behavioral inconsistency. The backlog of uncommitted real code (`azure_rbac_retry`, workspace module, new tests) is the most consequential drift — it should ship in the next commit cycle.

---

## 8. Prime Time?

**Verdict: ❌ NOT READY (for prime time) — ✅ READY (for run #3)**

**GO for run #3.** The infrastructure is aligned, the container is healthy, all tests pass, schema and code are synchronized. Run it.

**The gap between "run #3" and "prime time":**

| Gap | Owner | Effort | Priority |
|---|---|---|---|
| Oracle quality score not wired (no Anthropic key, no LaBSE sidecar) | Tank (Step 2) | 1–2 days | P0 for prime time — without quality score, there is no answer to "is this translation good enough to share?" |
| Step 1.5a cost guardrails not applied (`minReplicas: 0`, $25 budget alert) | Tank (Step 1.5a) | 0.5 day | P0 — money is leaking today |
| README lessons revamp (11 lessons, grouped, public voice) not committed | Scribe (after run #3 green + Manish sign-off) | 1–2h | P1 — public repo, public readers |
| `docs/auth.md` posture unresolved | Tank/Manish to decide, Scribe to execute | 30 min | P1 — live credentials loose in working tree |
| `public-lessons-curation` skill not on disk | Scribe (same commit as lessons revamp) | included | P1 |
| Uncommitted real code (workspace, azure_rbac_retry, new tests) | Trinity/Tank | 2–4h | P1 — divergence risk grows with time |
| Phase 1b (Oracle quality score in pipeline) | Trinity (Step 4, depends on Tank Step 2) | 3–5 days | Required for prime time |
| Per-book cost events (#97) | Trinity (Step 3) | 2–3 days | Required for full observability before prime time |

**The honest answer:** Prime time means a real reader opens a translated book and trusts it. Today we can execute the pipeline reliably and observe cost and gate status, but we cannot yet answer "is this translation good?" in a systematic, auditable way. That requires the Oracle quality score (Phase 1b). Prime time is 2–3 sprint cycles out, not 2–3 days.

**Run #3 is the last dev run before prime time prep begins.** What run #3 proves — that the Phase 1a dashboard works, that the new schema persists correctly, that the resume path is stable on a new book — is the last validation gate before shifting from infrastructure to quality.

---

## Follow-Up Tasks

| Task | Owner | When |
|---|---|---|
| Step 1.5a: `minReplicas: 0` in Bicep + $25 RG budget alert | Tank | Immediately (parallel with run #3) |
| Decide `docs/auth.md` posture (commit / gitignore / template) | Manish → Scribe | Before next commit cycle |
| Run #3 green → trigger Scribe: README lessons revamp + `public-lessons-curation` skill | Scribe | After run #3 green + Manish sign-off |
| Commit uncommitted real code (workspace, azure_rbac_retry, new tests) in a `chore` PR | Trinity/Tank | Next commit cycle |
| Step 2: Tank Oracle infra brief (Anthropic key in KV, LaBSE sidecar) | Tank | Post-run #3 |

---

*Assessment synthesized from: `tank-step7-deploy-DONE.md`, `decisions.md` (full drain as of `ac1cb46`), live filesystem checks, test runs. No agents spawned.*
# Tank — Step 7 Deploy Report: DONE

**Filed by:** Tank  
**Timestamp:** 2026-05-22T15:19:09-04:00  
**Cycle:** e2e run #3  
**Status:** ✅ DONE

---

## Revision & Image

| Field | Value |
|---|---|
| **Revision name** | `transpose-dev-app--0000008` |
| **Image digest** | `transposedevacr.azurecr.io/transpose@sha256:b2a3cdb692624eee926db66f323bc90805cf149d8d8dfa566e495175ce15d86b` |
| **ACR tags** | `sha-4e2d527`, `v5` |
| **Built from commit** | `4e2d527` (HEAD → origin/master) |
| **Build method** | `az acr build` (cloud-side, no local Docker) |
| **ACR** | `transposedevacr.azurecr.io` |
| **Resource group** | `transpose-sc` |
| **Previous revision** | `transpose-dev-app--rb2-7397468` (`transposedevacr.azurecr.io/transpose:v4`) |

---

## Health Check Results

| Check | Result |
|---|---|
| **kube-probe `/health`** | ✅ 200 OK — probes green within cold-start window |
| **App Insights telemetry** | ✅ Flowing — transmission 200, items accepted |
| **`/admin/api/books` (unauthenticated)** | ✅ 401 Unauthorized — NOT 500 |
| **`Failed to persist validation report` warnings** | ✅ None in 80-line cold-start log sample |
| **Revision active** | ✅ `active: true`, `trafficWeight: 100` |

---

## FQDN Tested

**App FQDN:** `transpose-dev-app.internal.yellowcoast-177ceb3f.swedencentral.azurecontainerapps.io`

Note: Ingress is **internal** (not external). The `/admin/api/books` check was performed from inside the container via `az containerapp exec` + `python3 urllib.request`. The 401 was confirmed from the `HTTPError: HTTP Error 401: Unauthorized` exception (urllib raises on 4xx). This is the correct production behavior — auth gate is active.

---

## Rollback Reference

If run #3 reveals a regression:
```
az containerapp revision activate \
  --name transpose-dev-app \
  --resource-group transpose-sc \
  --revision transpose-dev-app--rb2-7397468
```
No DB rollback needed — new schema is additive and backward-compatible with `:v4`.

---

## Ready for Run #3 Verdict

**✅ GO for run #3.**

All three Step 7 success criteria satisfied:
- New revision active with healthy probes ✓
- `/admin/api/books` → 401 (not 500) ✓
- No `Failed to persist validation report` cold-start warnings ✓

Schema at `3a9e1b27c4f1` (Step 6 DONE-IDEMPOTENT). New code (`4e2d527`) expects new schema. Both are aligned.

---

*Handoff note per Niobe's spec:* ✅ Tank: revision `transpose-dev-app--0000008` active. Health green. `/admin/api/books` returns 401 to unauthenticated. Ready for run #3.
