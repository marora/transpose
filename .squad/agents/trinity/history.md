# Trinity — Pipeline Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Chani (Dune cast) — see .squad/agents/_alumni/chani/history.md for accumulated knowledge

## Prior Work Summary (Archived from earlier sessions)

**2026-05-20 through 2026-05-21T01:48:** 
- Implemented Phase 1 workspace integration (TR-1 through TR-4): BookWorkspace, landing page generation, SAS URLs
- Built backfill CLI for pre-Stage-8 book workspace publishing
- Fixed local-dev blob RBAC dependencies with fallback pattern
- Fixed chunk stage oversized paragraph handling
- Fixed validation-report error path preservation

**All 353 unit tests passing. Workspace stage (Stage 8) live in pipeline runner.**

---

## Learnings

### 2026-05-21T11:40:56-04:00: Glossary U+FFFD scrub (Issue #89)

**Root cause:** `_clean_original_script` stripped FFFD at three points during aggregation, but variant merging in `_deduplicate_spelling_variants` could pull in raw `original_script` without re-cleaning. Bug manifested for `'shri'` (LLM-extracted, not in seed).

**Fix:** Promoted `_clean_original_script` to module level and added **final defensive scrub at entry-write time** (before `GlossaryEntry` built, before `CulturalTerm` written to DB). Belt-and-suspenders: earlier scrubs remain, final scrub is safety net regardless of path.

**Pattern:** For any pipeline stage normalizing/cleaning field values during aggregation, add **final write-time scrub**. Aggregation path may be complex; write site is always a single chokepoint.

**Tests added:** 5 new unit tests in `test_glossary.py :: TestCleanOriginalScriptUFFfd` — all passing.

### 2026-05-21T11:40:56-04:00: Gate heuristics need real-book calibration (Issue #90)

**Root cause:** `export_rendering` gate flagged "1 image(s) repeated 3+ times" as assembly dedup bug. On Shiv Sutra, chapter ornament/cover art legitimately repeats — design, not bug.

**Fix:** Threshold changed from `significant_dupes >= 1` to `>= 2` distinct large images each repeating 3+ times. One repeated image (regardless of size/frequency) never flagged.

**Pattern:** Gate thresholds must be validated against real-book corpora, not synthetic test PDFs. When gate is heuristic-based, ask: "can this pattern appear in well-formed real book?" If yes, threshold is too aggressive. A threshold blocking real exports is worse than one slightly loose.

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

