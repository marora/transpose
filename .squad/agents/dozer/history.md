# Dozer — Tester History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Thufir (Dune cast) — see .squad/agents/_alumni/thufir/history.md for accumulated knowledge

## Learnings

- **2026-05-21T11:00:50.468-04:00 — Pipeline smoke-test pattern:** Use a repo-local synthetic 2-page Hindi PDF plus a repo-local blob shim so the real runner, chunker, assemble/export, and workspace publish stages execute end-to-end without Azure dependencies; only translation and heavy post-export gates should be mocked. Keep a dual threshold (fast synthetic default, slower real-book override), assert either successful PDF+landing-page publish or a clean failure with validation-report output, and pin open issues as dedicated `xfail(strict=False)` regressions in the same file.
(Recast from Thufir — Matrix universe. All prior knowledge preserved in alumni archive.)

---

## 2026-05-20T22:55:00-04:00: Workspace Implementation Scoped — You're Next

**From:** Scribe (orchestration log)  
**Scope:** Workspace Abstraction + License/Provenance Product Framing now CLOSED

### Your Tasks (Phase 1)

1. **Unit tests:**
   - Workspace creation always produces `license.status = "rights-unknown"`
   - `provenance.source.acquired_at` is always set (never null) after creation
   - Promotion gate: returns false for `rights-unknown`, `claimed-public-domain`; returns true for `verified-public-domain`, `rights-cleared`

2. **Integration tests:**
   - Export/publish stage raises error (not warning) when license_status is ineligible
   - Blob ACL: private books don't leak via signed URLs

3. **Regression tests:**
   - Mutation to `license.status` appends entry to `license_history`
   - Does not silently overwrite; all mutations are logged

4. **DB constraint tests:**
   - Inserting a row with invalid `license_status` value is rejected
   - Check constraint is properly enforced

### Blocking On

- Tank's migration (DB schema in place)
- Trinity's implementation (workspace creation, export gate, license_history logging)

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Workspace + Archive Product Framing (FINAL)" (Niobe)
- `.squad/decisions.md`: "2026-05-20T22:52:32-04:00: BookWorkspace schema extension — license + provenance" (Morpheus)
- `.squad/log/2026-05-20T22-55-workspace-framing-close.md`: Full handoff details

---

## 2026-05-20T23:10:06.050-04:00: License + Landing Page Tests — Additional Phase 1 Work

**From:** Morpheus (Architect), Niobe (Product)  
**Scope:** Four-layer `rights-unknown` enforcement tests, landing page HTML validation, schema validation

### Your Added Tasks (Phase 1 — Priority)

**D-1: License Constraint Tests** (Four-layer enforcement: DB, app, metadata, tests)

Must write and maintain all five tests — they are binding:

| Test | Type | Assertion |
|------|------|-----------|
| `test_ingest_sets_rights_unknown` | Unit | `ingest_book(...)` → `book.license_status == 'rights-unknown'` |
| `test_ingest_rejects_license_param` | Unit | `ingest_book(..., license_status='claimed-public-domain')` raises `TypeError` (param doesn't exist) |
| `test_db_default_is_rights_unknown` | Integration | Raw SQL `INSERT INTO books (...) VALUES (...)` omitting `license_status` → row has `license_status = 'rights-unknown'` |
| `test_db_check_constraint` | Integration | Raw SQL `INSERT INTO books (..., license_status='made-up')` raises `IntegrityError` |
| `test_metadata_json_default` | Unit | Workspace creation writes `metadata.json` with `license.status == "rights-unknown"` |

- **Acceptance:** All five tests pass; D-1 tests written before Tank T-2 and Trinity TR-1 merge

**D-2: Landing Page Tests**

| Test | Assertion |
|------|-----------|
| `test_landing_page_contains_og_title` | Rendered HTML has `<meta property="og:title">` with correct content (book title + author) |
| `test_landing_page_contains_og_description` | Has `<meta property="og:description">` with translator_note or fallback |
| `test_landing_page_sas_urls_present` | HTML has source and translated PDF SAS URL links (non-empty) |
| `test_sas_url_readable` | Integration: generated SAS URL responds HTTP 200 with PDF content |

- **Acceptance:** All tests pass in CI; landing page generator (TR-3) validates via these tests

**D-3: `metadata.json` Schema Validation**

- Write schema validator (pydantic or jsonschema) for `metadata.json` covering mandatory-before-share fields: `title`, `author`, `landing_page_url`, `source_language`, `target_language`, `page_count`, `slug`, `share.source_pdf_sas_url`, `share.translated_pdf_sas_url`, `share.sas_expiry`, `share.generated_at`
- Validate in unit test against fixture and freshly created workspace
- **Acceptance:** Schema validator rejects `metadata.json` missing mandatory fields; passes on valid workspace metadata

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Niobe: Open Questions Closed — Shape A Product Rules Finalized"
- `.squad/decisions.md`: "2026-05-20: Morpheus: Architecture Addendum: Share URL + WhatsApp Preview Resolution"
- `.squad/orchestration-log/2026-05-20T23-10-06Z-morpheus-3.md`: Full technical handoff

### Blocking On

- Tank: T-2 (DB schema in place before D-1 integration tests can run)
- Trinity: TR-1, TR-2, TR-3, TR-4 (implementation before D-1, D-2, D-3 can validate)

### Unblocks

- Release readiness: All three agents can validate Phase 1 complete once Dozer tests pass

---

## 2026-05-20T23:30:00-04:00: D-1/D-2/D-3 Tests Delivered — Key Learnings

**Outcome:** All three deliverables implemented. Final suite: **763 passed, 9 skipped, 6 xfailed, 1 xpassed — 0 failures**.

### Files Created
- `src/transpose/workspace/__init__.py` — workspace package init
- `src/transpose/workspace/metadata_schema.py` — schema validator, `validate_metadata()`, `is_eligible_for_promotion()`, SAS URL regexes
- `tests/unit/workspace/__init__.py`
- `tests/unit/workspace/test_license_constraints.py` — D-1 (promotion eligibility, enum, ingest contract, workspace contract, export sentinel)
- `tests/unit/workspace/test_metadata_schema.py` — D-3 (11-case parametrized missing-field, enum, ISO 8601, SAS URL)
- `tests/unit/pipeline/test_landing_page.py` — D-2 (golden fixture integrity + Trinity TR-3 contracts)
- `tests/integration/test_license_db_constraints.py` — D-1 DB (skipped until `DATABASE_URL` + Tank T-2)
- `tests/golden/landing_page_fixture.html` — golden HTML snapshot

### Critical Learnings

#### 1. `fitz` local-import patch path
`fitz` (PyMuPDF) is imported *inside* `ingest.run()`, not at module level.
- ✗ `patch("transpose.pipeline.ingest.fitz")` — no-op (module has no `fitz` attribute at patch time)
- ✓ `patch("fitz.open")` — patches the global module cache entry directly

#### 2. `from . import X` bypasses `sys.modules` monkeypatching once package attribute is set
**Root cause of runner test contamination:**  
Importing `from transpose.pipeline.ingest import run` at module collection time causes Python to set `sys.modules["transpose.pipeline"].ingest` (the package attribute) to the real module. After that, `from . import ingest` in `runner.py` resolves via the package attribute — NOT `sys.modules["transpose.pipeline.ingest"]`. So `monkeypatch.setitem(sys.modules, ...)` in `_patch_stages` was silently bypassed.

**Fix:** Use `importlib.util.find_spec("transpose.pipeline.ingest")` for module existence checks at collection time. This checks for the module without importing it and without setting the package attribute. Import the actual module lazily inside the test body only.

#### 3. AsyncMock dangling coroutines and event loop contamination
Calling an async function that makes deeply-nested `AsyncMock` calls without properly awaiting all of them leaves "coroutine never awaited" `RuntimeWarning`s. The unawaited coroutines are GC'd after the test and corrupt event loop state for subsequent async tests. `@pytest.mark.filterwarnings("ignore::RuntimeWarning")` only suppresses the warning text, NOT the actual coroutine leak.

**Fix:** Avoid invoking the full `export.run()` pipeline before Trinity's license gate is implemented. Use lightweight sync tests instead (e.g., check for a sentinel attribute on the function).

#### 4. Contract test patterns
- For modules that **don't exist yet**: `importlib.util.find_spec()` + `@pytest.mark.skipif(not HAS_X, ...)`
- For modules that **exist but lack the feature**: `@pytest.mark.xfail(strict=False)` (NOT `strict=True` — the test may unexpectedly pass as implementation progresses)
- Never use async contract tests that invoke incomplete pipelines — always prefer sync sentinel checks

#### 5. Twitter Card spec gap (flagged to Morpheus)
Morpheus's landing page HTML template in `decisions.md §C` does NOT include `<meta name="twitter:card">` tags, but Dozer's D-2 spec requires testing for them. The golden fixture (`tests/golden/landing_page_fixture.html`) includes Twitter Card tags as an assertion target. Trinity must add them when implementing TR-3. See `.squad/decisions/inbox/dozer-twitter-card-gap.md`.


---

## 2026-05-21T16:08:19Z: Trinity Fixed Glossary & Export Gate Tests — 6 New Unit Tests

**From:** Scribe (orchestration log)  
**Context:** Issues #89 and #90 resolved via Trinity's defensive scrub + gate threshold tuning

### New Unit Tests That Landed

**Issue #89 — Glossary U+FFFD Scrub (5 tests):**
- `test_scrub_path_recoverable_string` — FFFD stripped, Devanagari preserved
- `test_reject_path_all_fffd` — entirely U+FFFD → empty string
- `test_clean_script_no_fffd_passthrough` — clean Devanagari unchanged
- `test_leading_trailing_fffd_stripped` — padding FFFD removed
- `test_mixed_fffd_and_latin_returns_empty` — Latin-only remainder → empty

All located in `tests/unit/pipeline/test_glossary.py :: TestCleanOriginalScriptUFFfd`

**Issue #90 — export_rendering Gate (1 updated, 1 new):**
- `test_fails_on_large_repeated_placed_images` — updated: now checks ≥2 distinct images (xref 777, 888) both repeating
- `test_passes_single_large_repeated_image_real_book` — new: ONE large image repeating 5 pages; gate must pass

Both in `tests/unit/pipeline/test_gates.py :: TestExportRenderingGate`

### Total Pipeline Tests
All 353 tests pass (6 additions + any existing).

### Takeaway for Dozer
- The `_clean_original_script` utility is now module-level and independently unit-testable (not nested inside `run()`)
- Export gate threshold is now parameterized: watch for future tuning as more real books run
- Both fixes are stable on shiv-sutra full-book completion

