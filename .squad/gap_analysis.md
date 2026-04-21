# Transpose E2E Gap Analysis — Beyond Issues #34–#39

**Date:** 2026-04-21  
**Analyst:** Stilgar  
**Context:** First real-world E2E run on 95-page Hindi book. Issues #34–#39 already filed.

---

## Issues Found (Not Captured in #34–#39)

### 1. Content Filter Blocks Not Distinguished from Transient Failures
**Description:** When Azure OpenAI content filter blocks a chunk, the retry logic in `llm_client.py:85` retries ANY Exception 3 times with exponential backoff. Blocked chunks (permanent failures) get the same retry treatment as rate limits (transient). This burns 6+ seconds per blocked chunk on futile retries.

**Impact:** On a 95-page book with 2 blocked chunks, 12+ seconds wasted on guaranteed-to-fail retries. At scale (100 books), hours of wasted compute. Blocks issue #34 resolution.

**Priority:** P1 (degrades production)

---

### 2. Per-Chunk Translation Failures Are Not Retryable
**Description:** In `translate.py:179–218`, when a chunk translation fails (transient error), the exception is caught, a `[TRANSLATION FAILED]` placeholder is created, and the pipeline moves to the next chunk. There is no per-chunk retry. Once a chunk is marked as translated (even with a placeholder), re-running translate skips it (line 91: `if chunk.id not in translated_chunk_ids`). Recovery requires manually deleting the translation record.

**Impact:** A transient Azure API error on 1 chunk of 72 requires operator to manually delete that record and re-run entire translate stage (possibly 1.5+ hours). Operational friction scales with book size.

**Priority:** P1 (operational burden)

---

### 3. Pipeline Progress Not Visible to Operators
**Description:** `runner.py` calls `ctx.state.set_progress()` and `translate.py` tracks progress at chunk level, but these values are never exposed. `PipelineOutput` has no progress field. The API `/status/{book_id}` endpoint returns only high-level status (running/completed/failed), not: "translate: 25/72 chunks done" or "export: 40% complete".

**Impact:** Operators cannot monitor long-running (3.6-hour) pipelines in real-time. Cannot distinguish hung vs. slow. Unknown which stage is bottleneck (issue #36: "3.6hr runtime, no per-stage timing visibility" — goes undiagnosed without progress tracking).

**Priority:** P1 (operational)

---

### 4. No Per-Translation Cost Visibility
**Description:** `runner.py:286-288` tracks total_tokens_used. `metrics.py` defines a `tokens_used` counter. But there is no mapping from tokens → cost. No cost calculation for OpenAI (Prompt: $0.03/1K, Completion: $0.06/1K) or Document Intelligence (~$2 per 1000 pages). The API does not expose token counts or cost. Addresses gap in issue #38 (cost tracking).

**Impact:** Operator cannot answer: "What did this book cost?" A 95-page book ≈ 25K tokens ≈ $0.5–1.5 translation + $0.2 OCR. Without visibility, budget goes blind.

**Priority:** P1 (production blocker)

---

### 5. Resume-From After Gate Failure Re-Translates Completed Chunks
**Description:** If a quality gate fails (e.g., `translation_completeness_gate` fails at translate stage), the pipeline halts. If the operator fixes the issue and retries with `--resume-from translate`, the runner will run translate AGAIN from scratch. The translate stage skips already-translated chunks (line 91), but on resume, the stage is invoked as if it's a fresh run, not a resumption. This results in duplicate DB inserts or silent overwrites.

**Impact:** Resume reliability undermined. Operator loses confidence if resume from a failed gate wastes $2–4 on duplicate translations.

**Priority:** P1 (operational reliability)

---

### 6. In-Memory API Job Tracker Lost on Container Restart (Critical)
**Description:** `api.py:38` maintains an in-memory `_jobs` dict. When a book is submitted via `/translate` (fire-and-forget), the job status is tracked in this dict. If the container restarts before export completes, all in-flight job status is lost. Callers of `/status/{book_id}` get 404 even though the book exists in the DB.

**Impact:** Multi-replica Container Apps deployments will route `/status` requests to different replicas. On any container restart (security patches, auto-scaling), in-flight job status evaporates. Unacceptable for production SLA.

**Priority:** P0 (production blocker)

---

### 7. Distributed Lock Has No TTL Enforcement (Critical)
**Description:** `cache.py:55` defines `acquire_lock(book_id, ttl=3600)` with a TTL parameter, but the parameter is unused. PostgreSQL `pg_try_advisory_lock()` provides session-level locks with no built-in timeout. If a pipeline crashes after acquiring the lock but before calling `release_lock()`, the lock persists indefinitely (or until the connection times out, hours later). Attempting to run the pipeline on the same book again hits the lock and bails out (line 197: "another pipeline run is in progress").

**Impact:** Pipeline crash leaves book permanently locked. Operator must manually kill the PostgreSQL session to unlock. On a 100-book batch, 1 crash can block all subsequent runs.

**Priority:** P0 (production blocker)

---

### 8. No Gate Performance Metrics
**Description:** `metrics.py` defines counters for `chunks_translated`, `tokens_used`, `pages_processed`, but no metrics for: gate execution time, gate failure rate, gate-specific pass/fail counts, or per-gate timing.

**Impact:** If a gate starts failing on 30% of books (e.g., glossary_integrity regression), there is no instrumentation to detect it. Operators discover the problem via manual spot checks, not monitoring.

**Priority:** P2 (observability)

---

### 9. Content-Filtered Chunks Not Retryable Without Manual Intervention (Critical)
**Description:** Related to #1 and issue #34. When a chunk hits a content filter block, there is no programmatic fallback (e.g., rephrase prompt, use less-filtered model). The `[TRANSLATION FAILED]` placeholder is permanent. Recovery requires manual: operator edits the chunk or source text, marks translation for retranslation, re-runs translate.

**Impact:** On religious/cultural texts (e.g., Osho's Vigyan Bhairav Tantra, issue #34: 2/72 chunks blocked), this is unacceptable. 100% of published books will have untranslated sections.

**Priority:** P0 (production blocker for content-sensitive domains)

---

### 10. Export Stage Produces PDFs Without Rendering Quality Validation (Critical)
**Description:** `export.py:30–110` generates ePub and PDF artifacts but does NOT validate output quality: no checks for font embedding success, glyph substitution failures, Devanagari rendering, PDF compression, or file integrity. Gate 6 (artifact_availability) checks only file size > 1KB. Gate 7 (production_readiness, called validate_production_readiness() in runner.py:403) checks structural presence (title, chapters exist) but not rendering quality (are Devanagari glyphs readable?). Issue #39 (Visual Comparison QA) reports Devanagari garbled in output PDF — this is why gates didn't catch it.

**Impact:** PDF can pass all gates and still be unpublishable. Devanagari font issues (issue #39) discovered only after export, too late to prevent artifact generation.

**Priority:** P0 (production blocker — direct cause of issue #39)

---

### 11. No Request Timeouts on LLM API Calls
**Description:** `llm_client.py:85–97` makes Azure OpenAI API calls without request timeouts. If Azure service is degraded and responses hang (not uncommon on multi-tenant services), the request will block indefinitely. The retry logic will wait for each attempt to complete before retrying. With translate stage concurrency=5 and 72 chunks, a single hung request can stall the entire stage.

**Impact:** Service degradation (normally 1-2 second response → 5-minute hang) can turn 3.6-hour pipeline into 12+ hours. No protection against slow providers.

**Priority:** P1 (reliability)

---

### 12. Database Connection Pool Not Sized for Concurrent Translate Stage
**Description:** `database.py` initializes asyncpg with default connection pool settings. The translate stage (concurrency=5, 72 chunks) makes DB calls per chunk (create_translation, set_progress). With default pool size (likely min=10, max=10), 5 concurrent tasks competing for connections can exhaust the pool, serializing subsequent chunks.

**Impact:** Connection pool bottleneck defeats concurrency optimization. Translate stage can run 2x–3x slower than expected.

**Priority:** P2 (performance)

---

### 13. No Environment Variable Validation at Startup
**Description:** `cli.py:20–24` initializes tracing at startup but does not validate that required environment variables are set (blob_storage_account_url, openai_endpoint, openai_deployment, postgres_host, postgres_user, postgres_db, etc.). If a variable is missing, the error occurs only when that service is first invoked (e.g., ingest stage tries blob storage). A misconfigured container can boot successfully but fail mid-pipeline.

**Impact:** Misconfigured container will crash in production. On auto-restart policies, will loop indefinitely. Startup health checks should validate config.

**Priority:** P2 (operational safety)

---

### 14. Translate Concurrency Hardcoded, Not Configurable
**Description:** `runner.py:276` hardcodes `concurrency=5` when calling `translate.run()`. This is not exposed to CLI (`--concurrency` flag) or API request body. Operators cannot tune concurrency based on book size (small books might benefit from higher concurrency; large books might hit Azure quota limits).

**Impact:** Cannot optimize pipeline for deployment constraints. Performance tuning requires code changes.

**Priority:** P2 (optimization)

---

### 15. No Test Coverage for Resume-From Functionality
**Description:** `tests/unit/pipeline/test_runner.py` has no tests for the `resume_from` parameter. `runner.py:149–172` implements resume logic, but there are no tests verifying: (a) correct stage selection, (b) idempotency across resume, (c) lock handling on resume, (d) exception handling on invalid resume_from stage.

**Impact:** Resume bugs go undetected in CI. Discovered in production when operator attempts to recover from a failed run.

**Priority:** P2 (test coverage)

---

## Priority Summary

| Priority | Count | Issues |
|----------|-------|--------|
| P0 (Critical) | 4 | #6 (in-memory job tracker), #7 (lock TTL), #9 (content filter retry), #10 (export validation) |
| P1 (High) | 6 | #1 (retry behavior), #2 (per-chunk retry), #3 (progress visibility), #4 (cost tracking), #5 (resume after gate), #11 (LLM timeouts) |
| P2 (Medium) | 5 | #8 (gate metrics), #12 (pool sizing), #13 (config validation), #14 (configurable concurrency), #15 (test coverage) |

---

## Recommended Action Plan

**Immediate (This Sprint):**
- Fix #6: Persist job status to PostgreSQL (not in-memory)
- Fix #7: Implement lock TTL with auto-cleanup on acquire
- Fix #10: Add font/glyph validation to export stage before artifact upload
- Fix #9: Add content-filter-aware retry with prompt rephrasing fallback

**Sprint 1:**
- Fix #1: Distinguish content filter errors from transient errors
- Fix #2: Implement per-chunk retry with backoff
- Fix #3: Expose progress in PipelineOutput and API
- Fix #4: Add cost calculation and cost tracking metrics
- Fix #5: Fix resume-from to not re-translate completed chunks
- Fix #11: Add request timeouts to LLM calls

**Sprint 2+:**
- Fix #8: Add gate execution time and failure rate metrics
- Fix #12: Size DB pool based on concurrency
- Fix #13: Add startup config validation
- Fix #14: Make translate concurrency configurable
- Fix #15: Add resume-from test coverage

---

## Key Insights

1. **Operational visibility is missing.** No progress tracking, no cost tracking, no per-chunk retry. 3.6-hour runs are blind.
2. **Critical production risks:** Job tracker not persistent, lock timeout not enforced, no fallback for content filters. These will cause production outages.
3. **Quality gates are incomplete.** Gates check structural presence, not rendering quality. Issue #39 (Devanagari garbling) passed all gates.
4. **Resume functionality is incomplete.** Cannot safely resume after a gate failure without re-translating completed work.
5. **Observability (metrics, progress, cost) is invisible.** Charts, budgets, and SLOs are impossible without this data.

---

