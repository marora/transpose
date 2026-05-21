---
updated_at: 2026-05-21T16:08:19Z
focus_area: Shiv Sutra e2e complete, pipeline hardened, 353 tests pass
active_issues: [hardening-in-progress]
---

# What We're Focused On

**Shiv Sutra first real-book e2e pipeline complete.** Fixed critical glossary (U+FFFD) and export gate issues. Pipeline validated end-to-end with artifacts published to Azure. Momentum: moving from one-off heroics to systematic pipeline hardening for multi-book runs.

## Recent Wins (Session 2026-05-21)

- **Issue #89 (FIXED):** Glossary U+FFFD character contamination — defensive final scrub + 5 unit tests
- **Issue #90 (FIXED):** export_rendering false positive on single repeated images (cover art, logos) — threshold raised to ≥2 distinct images
- **Shiv Sutra E2E:** Pipeline ran to completion with validation=PASS; 275KB ePub and 1.38MB PDF published to Azure
- **Unit test suite:** 353 tests, all passing (includes 6 new tests for #89, #90)

## Pipeline Hardening Status

| Component | Status | Tests |
|-----------|--------|-------|
| Glossary stage | ✅ Scrubbed | 5 new FFFD tests |
| Export rendering | ✅ Tuned | 2 gate tests |
| E2E validation | ✅ PASS | 353 pipeline tests |
| Artifacts | ✅ Published | Shiv_Sutra.epub, .pdf in Azure |

## Next: Multi-Book Runs

Morpheus pipeline hardening plan (P0 fixes #87, #86, #81) prioritized for 3–5 book ingestion. Focus: chunk invariants, translation timeout budgets, local artifact fallback.

