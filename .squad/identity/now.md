---
updated_at: 2026-05-21T14:41:45Z
focus_area: Shiv Sutra hardened + complete; performance/cost baseline documented; ready for multi-book scale
active_issues: []
---

# What We're Focused On

**Shiv Sutra is complete and production-ready.** Pipeline hardened (glossary U+FFFD scrub, export gate heuristics calibrated). Performance baseline documented (10h 32m wall time, $12.13 cost for 250-page book). Optimization backlog filed (issues #94, #95) for future throughput/cost improvements. Ready to ingest 3–5 additional books without rework.

## Recent Wins (Session 2026-05-21)

- **Issue #89 (FIXED):** Glossary U+FFFD character contamination — defensive final scrub + 5 unit tests
- **Issue #90 (FIXED):** export_rendering false positive on single repeated images (cover art, logos) — threshold raised to ≥2 distinct images
- **Shiv Sutra E2E:** Pipeline ran to completion with validation=PASS; 275KB ePub and 1.38MB PDF published to Azure
- **Public Access (FIXED):** Republished artifacts to `$web/shiv-sutra/` (Static Website path). User-accessible at `https://transposebooks.z13.web.core.windows.net/shiv-sutra/`
- **Landing Page Complete:** Both download buttons (source + translation) now functional and visible
- **Infrastructure Wiring:** `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` now flows through IaC and setup scripts for future books
- **Ops Clarity:** Manual republish checklist needed (issue #92); pipeline output is correct
- **Performance Telemetry:** Baseline cost + wall-time analysis complete; issues #94 (wall-time) and #95 (cost) filed as LOW-PRIORITY for future optimization
- **Unit test suite:** 353 tests, all passing (includes 6 new tests for #89, #90)

## Pipeline Hardening Status

| Component | Status | Tests |
|-----------|--------|-------|
| Glossary stage | ✅ Scrubbed | 5 new FFFD tests |
| Export rendering | ✅ Tuned | 2 gate tests |
| E2E validation | ✅ PASS | 353 pipeline tests |
| Artifacts | ✅ Published | Shiv_Sutra.epub, .pdf in Azure |
| Landing pages | ✅ Both links | source + translation visible |
| Performance baseline | ✅ Documented | Issues #94, #95 filed for future work |

## Next: Multi-Book Runs

Morpheus pipeline hardening plan (P0 fixes #87, #86, #81) prioritized for 3–5 book ingestion. Focus: chunk invariants, translation timeout budgets, local artifact fallback. Pipeline is ready for volume; optimization (wall-time, cost) is LOW-PRIORITY backlog.


