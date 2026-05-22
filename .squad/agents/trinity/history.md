# Trinity — Pipeline Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Chani (Dune cast) — see .squad/agents/_alumni/chani/history.md for accumulated knowledge

---

## 🔔 CROSS-AGENT: Observability Dashboard Work Incoming (2026-05-21T23:17:42Z)

**From:** Morpheus (Architect), Scribe (Orchestrator)  
**Status:** Architecture locked; GitHub issues pending

### YOUR TASKS: Issues #97, #99, #100 (3 issues, strict sequence)

**Priority:** SECOND (after Tank #98 auth middleware)

**Sequence matters:**
1. **#97 — Schema + Runner Instrumentation** (you own; depends on Tank #98 for auth test pattern)
   - `book_cost_events` table: append-only, stage-level telemetry
   - `cost_events.py` module: `record_stage_start()`, `record_stage_end()`
   - Modify `runner.py`: emit INSERT/UPDATE at stage boundaries (run_id already exists as `pipeline_start_time`)
   - Closes #93 (persistent cost tracking on failed/resumed runs)

2. **#99 — Dashboard API Routes** (depends on #97 schema existing)
   - `dashboard_api.py` module: `/admin/api/books`, `/admin/api/books/{id}/stages`, `/admin/api/projection?pages=N`
   - `projector.py` module: linear estimation, 3-book rolling window, pure functions
   - Register routes in `api.py` with Tank's Entra auth middleware
   - JSON responses, no pagination needed (MVP <10 books)

3. **#100 — Admin Frontend Static Files** (depends on #99 API routes done)
   - `web/admin/index.html`, `web/admin/app.js`, `web/admin/style.css`
   - Fetch API calls to `/admin/api/*` routes
   - Tables: books with totals, expandable stage breakdown, projection input
   - Cross-book trend chart (optional v1.1; table fine for v1)
   - Served by Container App from `/admin/` directory (aiohttp static middleware)

**Reference:** `.squad/decisions.md` — 2026-05-21T23:17:42-04:00 entry (Architecture Decision — sections 2, 3, 6)

---

## Prior Work Summary (Archived from earlier sessions)

**2026-05-20 through 2026-05-21T01:48:** 
- Implemented Phase 1 workspace integration (TR-1 through TR-4): BookWorkspace, landing page generation, SAS URLs
- Built backfill CLI for pre-Stage-8 book workspace publishing
- Fixed local-dev blob RBAC dependencies with fallback pattern
- Fixed chunk stage oversized paragraph handling
- Fixed validation-report error path preservation

**All 353 unit tests passing. Workspace stage (Stage 8) live in pipeline runner.**

---

## 🔔 CROSS-AGENT: Oracle Ships Translation Quality Score v1 (2026-05-22T11:35-04:00)

**From:** Oracle (Editorial), Scribe (Orchestrator)  
**Status:** DELIVERED — Phase 1b unblocked

### YOUR PATH NOW CLEAR FOR #99, #100

Oracle delivered **Translation Quality Score v1 spec — fully backed, no deferred LLM judgment.** This was the editorial blocker for Phase 1b dashboard quality column.

**Score composition:**
- **Tier 1 (deterministic, free):** Structural signals from gate details (OCR confidence, completeness, glossary, document structure, QA, production readiness)
- **Layer A (100% of chunks):** LaBSE multilingual embeddings for semantic-similarity (near-zero cost, self-hosted)
- **Layer C (5% stratified sample):** Claude Sonnet 4.5 cross-family judge rates fluency, cultural register, terminology nuance
- **Output:** Single 0–100 score; color bands ≥85 green / 65–84 amber / <65 red
- **Cost:** ~$0.16–$0.50/book (well under $3 target)

**Full spec:** `.squad/decisions.md` — Oracle Translation Quality Score v1 entry (post-merge from inbox)

### Your Dashboard Integration Path

1. **#97 Schema:** Add `quality_score` INTEGER to book cost events or separate table
2. **#99 API:** Return quality_score alongside cost breakdown in `/admin/api/books/{id}`
3. **#100 Frontend:** Display score + color band in books table, drill-down to judge sample comments

No changes to Trinity pipeline needed (judges run post-export as async layer per Oracle spec). Oracle's scoring layer will integrate separately via Tank infra.

### Blocks Lifted

- Phase 1b no longer gated on "what is good translation?" — score is defined
- Manish can see quality + cost + wall-time on same dashboard
- Team can calibrate quality/cost/speed tradeoffs per book

### Next: Tank's Turn

Tank must wire up **infrastructure for Layer A + C:** Anthropic API key (Key Vault) + LaBSE sidecar container + outbound HTTPS. Oracle's brief and full spec document all constraints. Niobe will file separate Tank brief.

---

## Learnings and Historical Context

See `.squad/agents/trinity/history-archive.md` for pre-2026-05-22 learnings, investigations, and improvements. Includes:
- Phase 1a dashboard architectural decisions and patterns
- Parallelism investigation for Shiv Sutra (partial parallelization, prompt overhead)
- Gate heuristic calibration (FFFD scrub strategy, export rendering threshold)
- Phase 1 workspace integration (TR-1 through TR-4)

---

**Tests updated:** 2 tests in `test_gates.py :: TestExportRenderingGate` — both passing.

### 2026-05-21T11:40:56-04:00: Azure blob containers provision timing

- Storage account had `$web`, `book-workspaces` but NOT `output` or `source-pdfs` (used by export stage)
- Blob client's `_should_fallback` only catches auth errors; `ContainerNotFound` is hard failure
- **Action:** `scripts/azure-setup.sh` should pre-create `output` and `source-pdfs` containers as part of storage account provisioning (created manually for Shiv Sutra run)

### 2026-05-21T11:40:56-04:00: Shiv Sutra e2e success

- Resumed from `glossary` after crash, 7 chunks, 0 translation failures
- With both fixes (#89, #90): `glossary_integrity` PASSED (186 terms), `document_structure` PASSED (3 chapters), `artifact_availability` PASSED
- Artifacts: `Shiv_Sutra.epub` (275 KB), `Shiv_Sutra.pdf` (1.38 MB) published to Azure Blob `output` container
- `overall: PASS` — pipeline completed to `exported` status
- **6 new unit tests added** (5 for glossary FFFD, 1 for export gate); total 353 tests passing

---


### 2026-05-21T12:17:57-04:00: Workspace publish Static Website URL wiring (Tank follow-up)

**Status:** Wired

Tank diagnosed that the Container App missing `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` env var, preventing workspace publish from targeting `$web/<slug>/`. Now wired through:
- `infra/modules/container-app.bicep` accepts and passes through the variable
- `infra/main.bicep` derives from storage account Static Website endpoint
- `scripts/azure-setup.sh` outputs the URL for local override
- `.env.example` documents the derivation

**Impact:** Future book runs will automatically publish to public Static Website path without needing manual URL injection or post-hoc republishing.

### 2026-05-21T17:45:28Z: Shiv Sutra landing — original scan link added

**Status:** Complete

Tank verified: Workspace stage (`Stage 8`) `source_url` threading is correct. Previous manual republish omitted the original link. No pipeline bug. Tank re-rendered landing.html with source_url and copied original PDF to `$web/shiv-sutra/source.pdf`. Both download buttons now functional.

**Learning:** Manual republishes are the ops gap, not the pipeline. Ops issue #92 filed for republish checklist.

---

### 2026-05-21T14:19:30.760-04:00: Cost Telemetry Investigation — Platform Learning (Tank)

**From:** Tank (cost forensics on Shiv Sutra)  
**Status:** Reference; no action needed  
**Related:** Issue #93 filed

Tank traced true Shiv Sutra cost through PostgreSQL operational tables (not `book_costs` table). Finding: `CostTracker.persist()` only writes `book_costs` rows on happy-path workspace completion. Failed/interrupted/resumed runs lose durable cost summary.

**For future:** When users ask about book cost post-run, always check:
1. `translations` table for OpenAI tokens (all runs retained)
2. `books.page_count` / `pages` for OCR (all runs retained)
3. Logs/App Insights for blob I/O only (reconstructed if needed)

**Implication for workspace stage:** Cost telemetry resilience is tracked in issue #93. Pipeline is correct; observability layer needs hardening.

---

### 2026-05-21T14:41:45-04:00: Pipeline optimization backlog filed

**Status:** Issues filed (no implementation started)

Per Manish's request, filed two LOW-PRIORITY optimization backlog issues based on Shiv Sutra telemetry:
- **Issue #94:** Wall-time optimization — target <2h for 250-page book (currently 10h 32m; OCR + translation bottlenecks identified)
- **Issue #95:** Cost optimization — target <$5 for 250-page book (currently $12.13; prompt overhead and model tier candidates identified)

Both reference book_id `723477a9-7ca4-4ba6-944c-3abef1ee92a4` and include investigation avenues (parallelization, prompt caching, chunk tuning, model downgrade, OCR caching). No decisions made — backlog for future investigation.

---

### 2026-05-22T15:19:09-04:00: Team update — Phase 1a shipped + priority ladder locked

**From:** Scribe (on behalf of Coordinator)  
**Status:** Session resumption; Steps 1–5 complete, Step 6 (Tank migrations) in progress

**Your Phase 1a has shipped:**
- Commits 405b8c4 (Entra auth), c61c87e (Phase 1a pipeline), 7397468 (gateway) on origin/master
- Two new migrations applied: license/provenance columns + `book_validation_reports` table
- GateResult now includes `duration_ms` field
- Dashboard API routes behind Entra auth; frontend static files served from `/admin/`
- Validation reports persisted best-effort on all terminal branches (success + error paths)

**Your investigation results referenced in priority ladder:**
- Parallelism investigation (2026-05-21T23:02:20) documented in `.squad/decisions.md`; parallelism defaults + Trinity brief already inboxed for phase 2
- Phase 1a dashboard shipped doc filed today (2026-05-22T15:40:25Z) with full spec + known gaps + Phase 1b unblocking list

**Next for you:** See `.squad/decisions.md` lines for priority ladder v2 (2026-05-22T15:19):
- Step 3: #97 (cost events table + per-stage telemetry) — **your next high-priority task**
- Step 4: Phase 1b (Oracle quality column wired to dashboard) — depends on Tank infra brief (Step 2) landing first
- Full ladder available in `niobe-priority-ladder-2026-05-22-v2.md` inbox entry (now merged into decisions)

---

