# Trinity — Pipeline Dev History Archive

**Archive period:** Pre-2026-05-22 learnings and investigations  
**Purpose:** Historical context for pipeline decisions and improvements  
**See also:** `.squad/agents/trinity/history.md` for current work

---

## Learnings from 2026-05-21

### 2026-05-22T15:40:25Z: Phase 1a dashboard shipped (issues #99 + #100)

**Status:** Shipped. 12/12 dashboard unit tests passing.

**Key architectural moves:**

1. **Validation report persistence is the load-bearing addition.** Pre-existing code only wrote `validation-report.json` to disk via `input.output_dir`, which made the dashboard impossible without re-reading per-run files. Added a `book_validation_reports` JSONB table + a best-effort `_persist_validation_report(ctx, book_id, report)` helper called from all three terminal branches in `run_pipeline` (success, QualityGateError, generic Exception). Never raises — observability MUST NOT block pipeline.

2. **`GateResult.duration_ms` field added.** Previously duration was only emitted to OTel metrics inside `_run_gate`. Stamping it onto the dataclass let the report carry it without re-plumbing the metrics pipeline. Backward-compatible — `duration_ms: float | None = None`.

3. **API shape is forward-compatible with #97.** The dashboard module ships with a `_COST_SERVICE_TO_STAGE` dict that maps `book_costs` rows to pipeline stages today (openai→translate, doc_intelligence→ocr, blob_storage→export). When #97 cost_events lands with per-stage tags, the data source swaps inside `_rollup_costs()` — response shape unchanged. Same for wall-time: stages emit `null` until per-stage events exist.

4. **Quality stub pattern for Oracle-blocked work.** Every endpoint returns `quality: {available: false, score: null, band: null, reason: "Awaiting Oracle spec…"}`. Frontend toggles a column on `document.body.classList.add("quality-on")` only when at least one book reports `available: true`. Result: Phase 1b is purely additive — drop in the real implementation, the UI auto-reveals.

**Patterns worth keeping:**

- **Drop-box validation report.** Persist authoritative outputs at the chokepoint (terminal branches of the orchestrator), never sprinkled through stage code. One write site = one place to mutate.
- **Append-only telemetry tables.** `book_validation_reports` mirrors `book_costs` (UUID PK, FK to books, JSONB payload, created_at default now()) — append, query latest with `ORDER BY created_at DESC LIMIT 1`. No mutation, easy to backfill, history preserved for free.
- **Static HTML public-unlisted + API-gated.** The shell loads for anyone; data only appears after MSAL PKCE token exchange. This matches Tank's middleware: `/admin/*` is auth-protected, including `/admin/api/*`, but the static index serves before the auth challenge so MSAL can run client-side.

**Tests:** 12 tests in `tests/unit/api/test_dashboard.py` covering both pure helpers (`_rollup_costs`, `_summarize_gates`, `_validation_summary_label`, `_wall_time_seconds`) and full endpoint paths (with Tank's Entra middleware + a `_FakeDb` injected).

**Note:** `test_non_admin_routes_remain_unaffected` was already failing on `master` HEAD (Settings missing `get_entra_authority_url`). Not caused by this work.

### 2026-05-21T23:02:20-04:00: Parallelism diagnosis for slow book runs (#94, #95, #96)

**Verdict:** Shiv Sutra was **partially** parallelized.

- **Translation:** real async parallelism is present and default-enabled. `runner.py` passes `translate_concurrency`, `translate.py` uses `asyncio.Semaphore(...)` + `asyncio.gather(...)` when concurrency > 1, defaults are `translate_concurrency=5`, and no `.env` override lowered it.
- **OCR:** the `ocr_concurrency` knob is currently inert. `ServiceContext` passes it into `OcrClient`, but `OcrClient.extract_pages()` still submits a single `begin_analyze_document(...)` call for the whole PDF and waits for one poller result. Commit `d5e46b4` explicitly described this as "stored for future per-page parallelism".
- **Prompt overhead matters almost as much as concurrency:** local `gpt-4o` tokenization estimates ~1,785 fixed prompt tokens per translation chunk before source text. On Shiv Sutra's 454 chunks, that is roughly ~810k repeated prompt tokens — about 70% of total prompt spend.
- **No rollback found:** git history and decisions showed no decision/commit that deliberately serialized the pipeline. The relevant change (`aecb19b`) did the opposite: it introduced parallel translation.

**Pattern:** After any slow run, verify concurrency at three layers: **setting exists → setting is wired → setting is actually consumed**. A stored knob is not a feature. Also separate **stage wall time** from **prompt-shape waste**; for LLM stages, high input:output ratios often indicate repeated scaffold cost.

### 2026-05-21T11:40:56-04:00: Glossary U+FFFD scrub (Issue #89)

**Root cause:** `_clean_original_script` stripped FFFD at three points during aggregation, but variant merging in `_deduplicate_spelling_variants` could pull in raw `original_script` without re-cleaning. Bug manifested for `'shri'` (LLM-extracted, not in seed).

**Fix:** Promoted `_clean_original_script` to module level and added **final defensive scrub at entry-write time** (before `GlossaryEntry` built, before `CulturalTerm` written to DB). Belt-and-suspenders: earlier scrubs remain, final scrub is safety net regardless of path.

**Pattern:** For any pipeline stage normalizing/cleaning field values during aggregation, add **final write-time scrub**. Aggregation path may be complex; write site is always a single chokepoint.

**Tests added:** 5 new unit tests in `test_glossary.py :: TestCleanOriginalScriptUFFfd` — all passing.

### 2026-05-21T11:40:56-04:00: Gate heuristics need real-book calibration (Issue #90)

**Root cause:** `export_rendering` gate flagged "1 image(s) repeated 3+ times" as assembly dedup bug. On Shiv Sutra, chapter ornament/cover art legitimately repeats — design, not bug.

**Fix:** Threshold changed from `significant_dupes >= 1` to `>= 2` distinct large images each repeating 3+ times. One repeated image (regardless of size/frequency) never flagged.

**Pattern:** Gate thresholds must be validated against real-book corpora, not synthetic test PDFs. When gate is heuristic-based, ask: "can this pattern appear in well-formed real book?" If yes, threshold is too aggressive. A threshold blocking real exports is worse than one slightly loose.

### 2026-05-20 through 2026-05-21T01:48: Phase 1 workspace integration

Implemented Phase 1 workspace integration (TR-1 through TR-4): BookWorkspace, landing page generation, SAS URLs. Built backfill CLI for pre-Stage-8 book workspace publishing. Fixed local-dev blob RBAC dependencies with fallback pattern. Fixed chunk stage oversized paragraph handling. Fixed validation-report error path preservation. All 353 unit tests passing. Workspace stage (Stage 8) live in pipeline runner.

---

