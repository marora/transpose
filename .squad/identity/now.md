---
updated_at: 2026-05-21T23:30:27Z
focus_area: Observability v1 build (5 GitHub issues, strict sequence). Target ship 2026-05-24 EOD. Parallelization & perf deferred until #101 complete. 3–5 books ready for multi-book validation.
active_issues: ["#98 Entra ID auth (Tank)", "#97 cost_events (Trinity)", "#91 SAS fix (Tank, parallel)", "#99 dashboard API (Trinity)", "#100 dashboard frontend (Trinity)", "#101 test coverage (Dozer)"]
---

# What We're Focused On

**Shiv Sutra production-ready. Pipeline hardened.** Observability/FinOps framing approved by Manish and architecture locked by Morpheus. Team now moving into implementation sprint: 5 GitHub issues, strict sequencing, 4-week timeline (Manish will feed 3–5 additional books during build).

## Current Session (2026-05-21T23:17:42Z)

### Manish Approval ✅ Complete

Manish answered three concrete gates for observability framing:
1. **Security:** Dashboard auth-protected (Entra ID, not IP allowlist)
2. **Metrics:** Stage-level granularity (8 stages: ingest, ocr, chunk, translate, glossary, assemble, export, workspace)
3. **Projections:** Auto-estimate cost/time from N-1 actuals (linear by page count)

### Morpheus Architecture ✅ Complete

**Executive decisions locked:**

| Question | Choice | Rationale |
|----------|--------|-----------|
| AuthN/AuthZ | Container App + Entra ID bearer tokens | No new infra, $0 cost, ships hours not days |
| Data path | Thin JSON API on Container App | Live Postgres queries, no pre-computed artifacts |
| Persistence | Append-only `book_cost_events` table | Stage-level durability, survives failed/resumed runs (closes #93) |

**No new Azure resources.** Existing Container App + Postgres.

**MVP boundary:** v1 ships with per-book cost inquiry, stage breakdown, linear projection. No real-time, no export, no multi-tenant.

### Implementation Sequencing

**5 GitHub issues, strict order:**

| # | Issue | Owner | Prerequisite | Status |
|---|-------|-------|--------------|--------|
| 98 | Entra ID auth infra | Tank | — | **BLOCKER** — Ship first |
| 97 | Append-only cost events + runner instrumentation | Trinity | Tank #98 | Second |
| 99 | Dashboard API routes + projector | Trinity | #97 done | Third |
| 100 | Admin frontend static files | Trinity | #99 done | Fourth |
| 101 | Test coverage (unit + integration) | Dozer | Trinity #100 done | Fifth |

**Constraint:** Manish directive "Parallelization MUST be enabled" still active, but perf work (#94, #95, #96) **deferred** behind observability implementation. Once observability ships, revisit parallelization.

**Audiobook:** Deferred pending observability completion. Cost structures orthogonal (TTS vs. OCR+translation). When audiobook pipeline launches, add telemetry to same dashboard (v1.1, not blocking v1).

## Decision Gates Completed

✅ Manish approves observability MVP (Niobe framing Option B)  
✅ Manish locks 3 concrete answers (auth, granularity, projections)  
✅ Morpheus designs architecture (Container App + Entra ID + append-only events)  
✅ **Niobe locks execution sequence + backlog tier** (2026-05-21T23:30:27Z)

### Execution Sequence (Niobe Recommendation)

**Strict order for observability v1:**

1. **#98 (Tank)** — Entra ID auth for /admin/ (2–4h) — **MUST SHIP FIRST**
2. **#97 (Trinity)** — Append-only cost_events + runner (4–6h) — depends on #98
3. **#91 (Tank)** — SAS generation fix (1–2h) — parallel with Trinity's #97
4. **#99 (Trinity)** — Dashboard API + projector (6–8h) — depends on #97
5. **#100 (Trinity)** — Dashboard frontend (2–4h) — depends on #99
6. **#101 (Dozer)** — Test coverage (TBD) — depends on #100

**Effort:** 20–25 billable hours Tank + Trinity over 2–3 sessions  
**Target ship date:** 2026-05-24 EOD

### Legacy Backlog Triage (Niobe)

**Close as stale (5 issues):** #73–77 (stale against current book format, metadata now implemented, image preservation deferred)  
**Re-label (2 issues):** #78 → squad:oracle (editorial), #79 → squad:trinity (pipeline)  
**Deferred (3 issues):** #92 (quality-of-life), #94–#95 (perf) — re-evaluate after observability ships

**Awaiting Manish approval** before batch close & label updates.

**Next gate:** GitHub issues filed + Tank starts #98 auth implementation.

## Recent Session History (2026-05-20 through 2026-05-21T23:17:42Z)

- **Issue #89 (FIXED):** Glossary U+FFFD character contamination — defensive final scrub + 5 unit tests
- **Issue #90 (FIXED):** export_rendering false positive on single repeated images — threshold raised to ≥2 distinct images
- **Shiv Sutra E2E:** Pipeline ran to completion with validation=PASS; 275KB ePub and 1.38MB PDF published to Azure
- **Public Access (FIXED):** Republished artifacts to `$web/shiv-sutra/` (Static Website path). User-accessible at `https://transposebooks.z13.web.core.windows.net/shiv-sutra/`
- **Landing Page Complete:** Both download buttons (source + translation) now functional and visible
- **Infrastructure Wiring:** `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` now flows through IaC and setup scripts
- **Performance Telemetry:** Baseline cost + wall-time analysis complete; parallelism investigation complete
- **Unit test suite:** 353 tests, all passing

## Next: Decision Implementation + Multi-Book Scale

Once Manish approves parallelism + observability decisions:
1. Apply translation concurrency defaults (or implement OCR batching if quota permits)
2. Build observability v1 (cost module + dashboard + Issue #93 fix)
3. Ingest 3–5 additional books with improved parallelization + cost visibility
4. Monitor wall time + cost performance on multi-book runs
5. Re-evaluate audiobook direction post-observability

**Hardening roadmap:** Still on track. Shiv Sutra production-ready. Ready for volume once decisions land.


