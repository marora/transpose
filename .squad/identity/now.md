---
updated_at: 2026-05-21T17:45:28Z
focus_area: Shiv Sutra landing page complete with both source + translation downloads, pipeline hardened
active_issues: []
---

# What We're Focused On

**Shiv Sutra publicly accessible with complete book packaging (source PDF + translation).** Landing page now shows both download buttons as designed. Diagnosed that workspace stage `source_url` threading is correct; manual republish in prior session was the ops gap. Ops issue #92 filed. Momentum: multi-book runs can proceed with confidence in pipeline output correctness.

## Recent Wins (Session 2026-05-21)

- **Issue #89 (FIXED):** Glossary U+FFFD character contamination — defensive final scrub + 5 unit tests
- **Issue #90 (FIXED):** export_rendering false positive on single repeated images (cover art, logos) — threshold raised to ≥2 distinct images
- **Shiv Sutra E2E:** Pipeline ran to completion with validation=PASS; 275KB ePub and 1.38MB PDF published to Azure
- **Public Access (FIXED):** Republished artifacts to `$web/shiv-sutra/` (Static Website path). User-accessible at `https://transposebooks.z13.web.core.windows.net/shiv-sutra/`
- **Landing Page Complete:** Both download buttons (source + translation) now functional and visible
- **Infrastructure Wiring:** `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` now flows through IaC and setup scripts for future books
- **Ops Clarity:** Manual republish checklist needed (issue #92); pipeline output is correct
- **Unit test suite:** 353 tests, all passing (includes 6 new tests for #89, #90)

## Pipeline Hardening Status

| Component | Status | Tests |
|-----------|--------|-------|
| Glossary stage | ✅ Scrubbed | 5 new FFFD tests |
| Export rendering | ✅ Tuned | 2 gate tests |
| E2E validation | ✅ PASS | 353 pipeline tests |
| Artifacts | ✅ Published | Shiv_Sutra.epub, .pdf in Azure |
| Landing pages | ✅ Both links | source + translation visible |

## Next: Multi-Book Runs

Morpheus pipeline hardening plan (P0 fixes #87, #86, #81) prioritized for 3–5 book ingestion. Focus: chunk invariants, translation timeout budgets, local artifact fallback.


