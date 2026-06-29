# QA Report — Transpose

## Round 1: Fresh Codebase Rubber Duck Review

**Date:** 2025-06-29
**Reviewer:** Ron (Hermes Agent)
**Scope:** Full codebase architecture, code quality, regressions
**Excluded (known issues):** #130 (chapter name repetition), #131 (images not embedded), #132 (links break due to content filter policy)

---

## Summary

| Metric | Value |
|--------|-------|
| Total findings | 16 |
| Blockers | 2 |
| Critical | 9 |
| Nice-to-have | 5 |
| Test suite status | 704 passed, 8 failed, 28 errors, 5 xfailed |
| Total tests collected | 942 |
| Source files reviewed | 129 Python files |

---

## Issues Filed

| # | GitHub | Classification | Title |
|---|--------|---------------|-------|
| 1 | #142 | 🔴 BLOCKER | Audiobook upload_bytes wrong argument order — runtime crash |
| 2 | #143 | 🔴 BLOCKER | Audiobook API routes never registered — all consumer URLs return 404 |
| 3 | #133 | 🟠 CRITICAL | Audiobook pronunciation lexicon always empty — glossary attribute mismatch |
| 4 | #134 | 🟠 CRITICAL | Dashboard STAGE_ORDER missing 'audiobook' — diverged from runner |
| 5 | #135 | 🟠 CRITICAL | Dashboard GATE_CATALOG missing audio_quality gate |
| 6 | #136 | 🟠 CRITICAL | Test suite red: 28 errors (missing pytest-aiohttp) + 8 failures |
| 7 | #137 | 🟠 CRITICAL | .env.example has wrong Entra ID env var name |
| 8 | #138 | 🟠 CRITICAL | docker-compose env vars missing TRANSPOSE_ prefix |
| 9 | #139 | 🟠 CRITICAL | Documentation gate count inconsistency — 3 files say 10, code has 11 |
| 10 | #140 | 🟠 CRITICAL | Metrics naming drift — documented KQL queries return zero results |
| 11 | #141 | 🟠 CRITICAL | architecture.md references Redis (removed) |
| 12 | #144 | 🟢 NICE-TO-HAVE | Dead metrics in metrics.py — never recorded |
| 13 | #145 | 🟢 NICE-TO-HAVE | Dead constants (mastering.py, translate.py) |
| 14 | #146 | 🟢 NICE-TO-HAVE | project-structure.md missing 10+ modules |
| 15 | #147 | 🟢 NICE-TO-HAVE | 6 env vars bypass Settings class |
| 16 | #148 | 🟢 NICE-TO-HAVE | Audiobook transcription quality lacks wow factor |

---

## Architecture Assessment

### What's Sound
- Pipeline stage modularity — clean Input/Output dataclasses, DB-mediated communication
- Idempotent + resumable design — each stage re-runnable from checkpoint
- Quality gate system — 11 gates covering OCR through production readiness
- Service layer consistency — all clients: lazy init, DefaultAzureCredential, close()
- Translation error handling — graduated 4-stage content filter fallback
- Test suite design — 942 tests, golden reference fixtures, proper async mocking
- Cultural term preservation — seed glossary + LLM detection + dedup + NFC normalization

### What Needs Attention
- **Audiobook stage (Stage 8)** shipped with 3 runtime bugs blocking production use
- **Code-code consistency** — runner.py vs dashboard.py constants diverged
- **Documentation drift** — systemic across 5+ docs (gate counts, metrics, Redis references)
- **Test dependencies** — pytest-aiohttp missing, 28 tests can't run
- **Env var management** — split between Settings class and raw os.environ.get()

---

## Test Coverage Summary

| Category | Files | Coverage |
|----------|-------|----------|
| Pipeline stages (unit) | 16 test files | ✅ All 9 stages covered |
| Services (unit) | 7 test files | ✅ All major clients covered |
| Quality gates (unit) | 2 test files | ✅ All 11 gates tested |
| API (unit) | 4 test files | ⚠️ 28 errors (missing fixture) |
| Integration | 3 test files | ✅ Pipeline flow, cultural preservation, audiobook |
| Regression | 4 test files | ✅ Golden reference, production readiness |
| Observability | 3 test files | ✅ Cost events, projector, oracle judge |
| Models | 1 test file | ✅ Core entities |

**Modules with no dedicated tests:** tracing.py, queries.py, workspace.py (indirect only)

---

## Current State

### What Works
- Full translation pipeline (Stages 1-7): ingest through export
- Quality gates fire correctly on golden reference corpus
- Resume-from functionality (code works, tests need updating)
- Admin dashboard API (when pytest-aiohttp is installed)
- Cost tracking and observability (minus dead metrics)

### What's Broken
- Audiobook generation crashes on upload (wrong arg order)
- Audiobook consumer API unreachable (routes not registered)
- Audiobook pronunciation lexicon empty (attribute mismatch)
- 28 API tests can't run (missing test dependency)
- docker-compose local dev broken (env prefix mismatch)

### Known Limitations (not bugs)
- TTS pronunciation lexicon only covers 14 of ~200 cultural terms
- Content filter fallback handles ~2-3% of chunks (by design)
- WeasyPrint PDF rendering has title page overflow edge case

---

## Deferred Items (filed but not blocking delivery)

- #144: Dead metrics cleanup
- #145: Dead constants cleanup
- #146: project-structure.md refresh
- #147: Centralize env vars into Settings
- #148: Audiobook quality polish (prosody, transitions, emphasis)

---

## Next Steps

1. Fix blockers #142 and #143 (audiobook unusable without these)
2. Fix #133 (pronunciation lexicon)
3. Fix #136 (test suite health — add pytest-aiohttp, update assertions)
4. Fix #134 + #135 (dashboard constants)
5. Fix #137 + #138 (developer setup broken)
6. Documentation sweep: #139 + #140 + #141

Round 2 rubber duck after blockers + criticals are resolved.
