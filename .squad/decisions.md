# Squad Decisions

## Active Decisions

### Decision: Implementation Patterns — Chani's Core Implementation
**Author:** Chani  
**Date:** 2026-04-17  
**Status:** Active  

Centralized service container (ServiceContext) passed to all pipeline stages. Comprehensive CRUD methods in Database class for data access. Multi-part LLM prompts with seed glossary injection + JSON mode for structured output. Digital-first OCR strategy: PyMuPDF first, fall back to Document Intelligence. Paragraph-boundary chunking with structural detection. Sequential translation with previous-context passing for consistency. Glossary aggregation with term normalization and occurrence counting. HTML-based document assembly with chapter grouping. Parallel ePub/PDF export from same HTML source.

**Key implementation patterns:** ServiceContext owns service lifecycle, all stages receive ctx parameter, parameterized SQL queries, tenacity retry logic, JSON serialization for complex fields.

---

### Decision: Infrastructure — Phase 1 Complete
**Author:** Idaho  
**Date:** 2026-04-17  
**Status:** Active  

Complete Azure infrastructure provisioned via Bicep with Managed Identity authentication (zero secrets in code). SKU/tier choices: PostgreSQL Burstable B1ms, Redis Basic C0, Storage Standard_LRS, Container Apps 1 core/2Gi with 0-3 replicas. Phase 1 prioritizes developer velocity with public access enabled; Phase 2 adds VNet/Private Endpoints. Entra-only PostgreSQL authentication. Redis password in Key Vault. Application Insights + Log Analytics for observability. Docker multi-stage build with WeasyPrint dependencies, non-root user.

**Key decisions:** Modular Bicep organization, lazy service initialization in ServiceContext, output chaining between modules, production hardening checklist included.

---

### Decision: Test Strategy for Transpose Pipeline
**Author:** Thufir  
**Date:** 2026-04-17  
**Status:** Active  

Comprehensive test suite: 147 total tests (10 existing + 137 new). Unit tests mock service layer (Database, Cache, BlobClient, OcrClient, LlmClient) via fakeredis and AsyncMock. Integration tests validate pipeline flow end-to-end with mocked SDKs. Contract-based testing validates API contracts from `docs/api-contracts.md`, not implementation details. Cultural term preservation (P0): 16 parametrized tests for Hindi/Punjabi cultural terms (dharma, karma, atman, moksha, sangat, langar, etc.). Fixtures provide realistic test data (real UUIDs, actual cultural text, proper token counts).

**Test organization:** 15 test files across `tests/unit/` (11 files, 120 tests) and `tests/integration/` (2 files, 21 tests), plus 2 preserved test files. All passing. All ruff clean.

---

### Decision: Pipeline Architecture
**Author:** Stilgar  
**Date:** 2026-04-17  
**Status:** Active  

Transpose uses a 7-stage sequential pipeline: Ingest → OCR → Chunk → Translate → Glossary → Assemble → Export. Each stage is an independent Python module with typed input/output contracts. Stages communicate through PostgreSQL (source of truth and orchestration state). Quality gates block stage transitions.

**Key Decisions:**
1. Staged pipeline, not event-driven (simpler to debug, resume, reason about; event-driven is Phase 2)
2. All stages idempotent — re-running skips completed work (books are too expensive to reprocess)
3. Services wrap Azure SDKs — pipeline stages never call Azure directly (always through `services/`)
4. Managed Identity everywhere — no secrets in code (non-negotiable)
5. JSON mode for LLM output — structured extraction of translation + cultural terms in one call
6. Seed glossary + LLM detection for cultural terms (seed catches ~60 known terms; LLM catches the rest)
7. ePub-first, PDF from same HTML source — one canonical format, two renderings
8. PostgreSQL for persistent state, Redis for ephemeral state (losing Redis loses nothing permanent)
9. Python 3.12+ with src layout, hatch build, ruff lint, pytest (modern conventions)
10. `from __future__ import annotations` in all modules (forward-compatible typing)

**Impacts:**
- **Chani (Implementation):** Implement stages following the contracts in `docs/api-contracts.md`. Each `run()` function is async.
- **Idaho (Infra):** Provision Azure Container Apps, PostgreSQL Flexible Server, Redis, Document Intelligence, OpenAI, Blob Storage, App Insights. All with Managed Identity.
- **Thufir (Testing):** Test structure mirrors source. Unit tests mock service wrappers. Integration tests hit real Azure services.

**Key Files:**
- `docs/architecture.md` — The bible
- `docs/api-contracts.md` — Stage input/output contracts
- `docs/project-structure.md` — Directory layout
- `pyproject.toml` — Dependencies and build config
- `src/transpose/config/seed_glossary.py` — Curated cultural terms

### Decision: PDF Font Embedding Strategy

**Author:** Chani  
**Date:** 2026-04-18  
**Status:** Active  

Embed `NotoSansDevanagari.ttf` into generated PDFs using WeasyPrint's `@font-face` CSS declaration with `file://` URL and `FontConfiguration`. Font path resolved dynamically relative to repo root. Separate CSS into `CSS()` object with `font_config` parameter for proper font processing.

**Rationale:** WeasyPrint doesn't auto-discover fonts. Without explicit configuration, Devanagari text renders as tofu. Solution uses CSS `@font-face` (declarative, portable, standard) with dynamic path resolution (avoids hardcoded paths breaking across environments).

**Impact:** Devanagari text now renders correctly. PDFs display cultural terms (dharma, karma, moksha) in original script. ~600KB file size increase per PDF (font embedding overhead). Performance negligible (WeasyPrint caches parsed fonts).

**Implementation:** Tested in `tests/unit/test_export_visual.py`. All 12 visual regression tests passing.

---

### Decision: Visual PDF Testing Strategy

**Author:** Thufir  
**Date:** 2026-04-18  
**Status:** Active  

Add visual regression testing for PDF output using PyMuPDF (fitz) to inspect generated PDFs. Tests validate layout (title page fits, no overflow), text extraction (Devanagari renders correctly, not tofu), page structure (expected page counts), and edge cases (empty chapters, special characters, large glossaries).

**Rationale:** Visual bugs (page overflow, Devanagari rendering) cannot be caught by unit tests mocking PDF generation or contract tests validating types. Visual tests generate actual PDFs and inspect them with PyMuPDF.

**Implementation:** `tests/unit/test_export_visual.py` with 12 tests covering title page layout, Devanagari rendering, mixed script, glossary, page counts, and edge cases. Tests use real PDF generation, not mocked. PyMuPDF text extraction validates rendering quality.

**Impact:** Regression testing established for PDF features. Tests pass once font embedding fixed. Provides confidence for future PDF enhancements (headers, footers, styling).

---

### Decision: HTTP API as Container Entrypoint

**Author:** Chani  
**Date:** 2026-04-18  
**Status:** Active  

`src/transpose/api.py` is the container entrypoint (`python -m transpose.api`). aiohttp chosen over FastAPI — lighter weight, async-native, no Pydantic v2 conflicts. `/translate` accepts `blob_uri` (not file uploads) — PDFs must be in blob storage first. Pipeline runs in background via `asyncio.create_task`. Status polled via `/status/{book_id}`. In-memory job tracker acceptable for single-replica; multi-replica would need Redis/DB.

**Impact:** Pipeline has two entry points (CLI + HTTP), both through `PipelineInput → run_pipeline`. No interface change for pipeline stages.

---

### Decision: Serverless-First Architecture

**Author:** Mani (via user directive)  
**Date:** 2026-04-17  
**Status:** Active  

Drop Redis entirely. Use PostgreSQL auto-pause (Flex Server) for near-zero idle cost. Keep Container Apps scale-to-zero. Pipeline runs infrequently — optimize for zero recurring cost when not in use. Replace Redis-backed pipeline state/locks with PostgreSQL equivalents.

**Rationale:** Pipeline runs infrequently, no value in always-on Redis/PostgreSQL costs. Targets near-zero cost when idle.

**Impact:** Chani replaced Cache class (Redis) with PipelineState (PostgreSQL). Uses `pg_try_advisory_lock` for distributed locks. No interface change for pipeline stages.

---

### Decision: WSL2 Firewall Rule for Azure PostgreSQL

**Author:** Chani  
**Date:** 2026-04-18  
**Status:** Active — needs review before production  

WSL2 NAT presents different outbound IP than Windows host. Added `AllowAll` firewall rule (`0.0.0.0 - 255.255.255.255`) to `transpose-dev-psql` to unblock local dev. Intentionally broad for convenience.

**Action Required:** Before real data enters database, tighten rule to actual WSL2 NAT IP or use VNet/private endpoint.

**Also Notable:** asyncpg `ssl='require'` works correctly once TCP connectivity established. PGSSLCRL/PGSSLCRLDIR workaround applied in `cli.py` at module level.

---

### Decision: ACR Deployment Pipeline + External Ingress

**Author:** Idaho  
**Date:** 2026-04-17  
**Status:** Active  

Deployed Transpose pipeline code to `transpose-dev-app` via ACR. Image pull uses Managed Identity (AcrPull role) — no registry credentials stored. External ingress enabled for dev testing. FQDN: `transpose-dev-app.yellowcoast-177ceb3f.swedencentral.azurecontainerapps.io`.

**Decisions:**
1. ACR with Managed Identity pull (no admin credentials)
2. External ingress for dev (revert to internal for production)
3. PostgreSQL password in env var (temporary; Phase 2 use Key Vault reference)
4. Image tagging: `transpose:v1`, `transpose:v2`, etc.

**Phase 2 TODO:** Move PG password to Key Vault reference, revert to internal ingress, add custom domain.

---

### Decision: Serverless Infrastructure Pivot

**Author:** Idaho  
**Date:** 2026-04-17  
**Status:** Active  

Removed Redis (cache.bicep), updated Key Vault (removed Redis secret), updated Container App (removed Redis env vars), updated docker-compose (removed Redis service). Added pipeline_state table to init-db.sql. PostgreSQL auto-stop noted (post-deployment CLI). Cost estimate updated: ~$0/mo idle.

**Rationale:** User directive — pipeline runs infrequently, drop always-on services to minimize recurring costs.

**Impact:** Chani updated cache.py to use PostgreSQL. Tests using fakeredis rewritten to use PostgreSQL mocks.

---

### Decision: User Identity Clarification

**Author:** Manish (via Copilot)  
**Date:** 2026-04-18  
**Status:** Active  

User's name is **Manish**, not Mani. All team references and documentation use "Manish" for clarity.

**Rationale:** Explicit user correction captured for team memory.

**Impact:** Update all past references (decisions, logs, code comments) from "Mani" → "Manish".

---

### Decision: PDF/ePub Export Enhancements — Cover, ToC, Page Numbering

**Author:** Chani  
**Date:** 2026-04-19  
**Status:** Active  

Enhanced PDF and ePub export with three tightly coupled features:

1. **Cover page** uses styled title (32pt), optional subtitle from `manuscript.metadata["subtitle"]`, decorative separator, and author. ePub gets a dedicated `cover.xhtml` as the first spine entry.

2. **Table of Contents** page renders `manuscript.table_of_contents` (built by assemble stage) between cover and first chapter. Only appears when ToC data exists. ePub ToC uses ebooklib's built-in NCX/Nav — no custom rendering needed.

3. **Page numbering** via CSS `@page` counters: no number on cover, roman numerals on front matter (ToC), arabic from chapter 1 onward via counter-reset div.

**Key constraints:**
- Title page `padding-top` stays at 3cm (not 5cm) to prevent overflow on long titles
- Subtitle is opt-in via metadata, not auto-detected
- All three features share CSS and HTML ordering — must be changed together
- Devanagari font embedding (`@font-face` + `FontConfiguration`) is untouched

**Impact:** Thufir — visual regression tests may need updating if ToC data is added to test manuscripts (currently `table_of_contents` defaults to empty, so ToC page doesn't render in existing tests). All 223 tests pass as-is.

---

### Decision: Translator's Foreword — LLM-Generated Front Matter (Issue #12)

**Author:** Chani  
**Date:** 2026-04-19  
**Status:** Active  

Auto-generated Translator's Foreword added to the assemble/export pipeline. The foreword is generated via `LlmClient.chat()` using the top 15 cultural terms from the glossary. It is stored in `manuscript.metadata["foreword"]` (not a new model field) so it can be edited post-generation without schema changes.

**Key decisions:**
1. Foreword stored in metadata dict — avoids Manuscript model/DB migration, remains editable
2. `LlmClient.chat()` added as generic freeform prompt method — reusable for future tasks (e.g., back-cover blurb)
3. Foreword generation is non-fatal — failure logs a warning and produces output without foreword
4. Placement: after TOC, before Chapter 1 (front matter) in both ePub and PDF
5. ePub gets a separate `foreword.xhtml` in the spine; PDF gets a `foreword-page` div with page-break-after

**Impact:**
- **Thufir:** 6 new tests added (2 assemble, 4 export). Visual regression tests may want a foreword-specific PDF test.
- **Idaho:** No infra changes needed.
- **Stilgar:** No architecture change — foreword is an optional enrichment step within the existing assemble stage.

---

### Decision: Defense-in-Depth NFC Normalization for Indic Script (Issue #9)

**Author:** Chani  
**Date:** 2026-04-19  
**Status:** Active  

Every pipeline stage that touches `original_script` (Devanagari/Gurmukhi) text now independently applies `unicodedata.normalize('NFC', text)` before storing or rendering. Shared helper lives in `src/transpose/utils/unicode.py`.

**Touchpoints:** translate.py (extraction), glossary.py (aggregation), export.py (ePub + PDF rendering), seed_glossary.py (seed read).

**Rationale:** NFC normalization is idempotent and near-zero cost. By normalizing at every layer boundary, we guarantee correct rendering regardless of whether upstream stages (OCR, LLM, seed data, future integrations) emit NFC or NFD. This eliminates an entire class of "text looks garbled" bugs.

**Impact:** Fixes issue #9. No model or interface changes. All 223 tests pass.

---

### Decision: Artifact Availability Gate — Local Dev URI Support

**Author:** Chani  
**Date:** 2026-04-19  
**Status:** Active  

The `artifact_availability_gate` in `src/transpose/pipeline/gates.py` now accepts both cloud URIs (HTTP/HTTPS) and local file paths (absolute paths starting with `/`).

**Problem:** First E2E validation run failed the artifact gate because local dev mode writes to filesystem instead of blob storage. Gate only accepted HTTP URIs, causing false positive failures on valid local artifacts.

**Solution:** Modified URI validation to allow both patterns:
```python
if uri and not (uri.startswith("http") or uri.startswith("/")):
    failures.append(f"{fmt} artifact has invalid URI: {uri}")
```

**Impact:** 
- Local dev E2E runs now pass artifact gate
- No impact on cloud pipeline (blob URIs always start with `https://`)
- Thufir updated gate tests to cover both URI patterns

---

### Decision: Chapter Title Extraction for Multi-Script Documents

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  

The assemble stage now extracts English chapter titles from translated text instead of using source-language (Devanagari/Gurmukhi) chapter references.

**Problem:** 
1. E2E validation run produced 38 pages instead of expected 14 (10-page source)
2. Root cause: Source-language chapter refs (sometimes containing full chapter text, not just titles) were used as chapter headers in HTML and ToC
3. This caused two issues:
   - ToC page inflation (4 pages instead of 1)
   - Mixed-language output (English book with Devanagari headers)

**Solution:** Implemented `_extract_chapter_title(chapter_chunks, fallback)` in `src/transpose/pipeline/assemble.py`:
- Extracts English title from first translated chunk using regex patterns:
  - "Chapter N: Title" format (common in translation output)
  - Title-case lines like "Introduction"
  - First non-empty line as fallback
- Maximum title length check (100 chars) to prevent using paragraph text as chapter title

**Result:** Page count normalized from 38 to 14 pages (matches source).

**Impact:**
- Fixes ToC inflation (issue #13)
- Fixes mixed-language output (issue #6)
- Chani added regression tests asserting `page_count ≤ 1.5 × source_page_count` to catch this bug type in future

---

### Decision: Blocking Quality Gates — Version 2 (Proof-Based Definition of Done)

**Author:** Stilgar (recorded from Manish directive)  
**Date:** 2026-04-19  
**Status:** Active  

Established proof-based Definition of Done: nothing is "done" without artifacts generated, published with stable links, validation report attached, and all 5 quality gates passing.

**Five blocking quality gates:**

| Gate | Placed After | Key Criteria |
|------|--------------|--------------|
| ocr_sanity | OCR stage | Zero garbled blocks; confidence ≥ 0.95 on ≥ 95% of pages; no U+FFFD corruption |
| translation_completeness | Translation stage | 1:1 source→target chunk mapping; zero silent passthrough; tagged [REVIEW REQUIRED] on failures |
| glossary_integrity | Glossary stage | No mixed scripts; no garbled transliterations; required seed terms render correctly; NFC-normalized |
| document_structure | Assemble stage | Cover + ToC + Foreword + all chapters present; chapter count matches source; no mixed-language bleed |
| artifact_availability | Export stage | PDF + ePub artifacts generated with stable URIs (HTTP or local file path); downloadable/openable |

**Implementation Details:**
- Duck-typed inputs using `getattr()` to avoid circular imports
- GateResult dataclass with `passed`, `failures`, `details`, `timestamp`
- QualityGateError exception wraps GateResult for pipeline abort
- Validation report (JSON) written to output dir, includes all gate results
- CI enforcement via `.github/workflows/quality-gates.yml` — PRs cannot merge on gate failure

**E2E Results (2026-04-19):** 5/5 gates PASS

**Impact:**
- Eliminates ambiguity about "done"
- CI enforcement prevents quality regression
- All 11 open issues now have proof-based closure path

---

### Decision: Golden Reference Regression Testing

**Author:** Thufir  
**Date:** 2026-04-19  
**Status:** Active  

Golden reference data (`tests/golden/`) establishes the objective truth for pipeline output quality. Regression tests (`tests/regression/`) compare candidate output against these files.

**Key Decisions:**
1. Golden data is updated intentionally, never automatically — a failing test means "investigate", not "overwrite"
2. Regression tests are marked `@pytest.mark.regression` + `@pytest.mark.slow` to separate from fast unit tests
3. Glossary golden reference uses NFC-normalized Devanagari from seed_glossary.py (42 entries covering all Hindi + philosophical terms)
4. Page count test uses 1.5× source multiplier — immediately caught the existing 3.8× page inflation bug
5. Source text leak detection uses regex for 4+ consecutive Devanagari characters with spaces (sentences) while allowing inline preserved terms

**E2E Results (2026-04-19):** 20/20 regression tests PASS

**Impact:**
- Page inflation bug (38 pages) now fails as regression test
- Future refactoring cannot silently degrade output quality
- Provides objective proof for Definition of Done

---

### Decision: CI/CD Enforcement — Quality Gates in GitHub Actions

**Author:** Stilgar  
**Date:** 2026-04-19  
**Status:** Active  

CI pipeline (`.github/workflows/quality-gates.yml`) runs all 5 quality gates on every PR to main. PRs cannot merge if any gate fails.

**Workflow Details:**
- Triggered on push to main and PRs to main
- Runs full validation suite (ocr_sanity, translation_completeness, glossary_integrity, document_structure, artifact_availability)
- Writes validation report to workflow artifacts
- Blocks merge on gate failure
- Comments on PR with gate status, artifact links, validation report link

**Impact:**
- Quality regressions caught before merge
- Proof-based closure enforced at CI level
- Team visibility on gate status via PR comments

---

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
- Proof-based Definition of Done: artifacts + gates + validation report required for closure

### Decision: Strip Duplicate Chapter Titles from Translated Content

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  

LLM translations start each chunk with its chapter heading (e.g., "Chapter 2: Yoga and Meditation — Physical and Spiritual Discipline"). The assemble stage already renders a separate `<h1>` from the extracted title. A new `_strip_leading_chapter_title()` helper now removes the first line of translated text when it matches a chapter-heading pattern, preventing duplication in the output.

**Also fixed:**
- Foreword cleanup: `_clean_foreword()` strips LLM placeholder signatures like "[Translator's Name]"
- Foreword page numbering: `.foreword-page` now uses `page: frontmatter` CSS for roman numerals

**Impact:** Publishable-quality output — no visible duplications, clean foreword, consistent page numbering. No model or contract changes.

**Known limitation:** WeasyPrint's ToUnicode CMap for Noto Sans Devanagari produces garbled text extraction (copy/paste) despite correct visual rendering. This is an upstream WeasyPrint issue. Affects accessibility/search but not visual quality.

---

### Decision: Golden-Targeted QA Gate Design

**Author:** Thufir  
**Date:** 2026-04-20  
**Status:** Active  

The pipeline needed a post-export quality gate that compares actual output against a known-good reference translation — not just structural checks, but content completeness, script hygiene, and glossary integrity.

**Decision:** Implemented a 3-artifact comparison system:
1. **Golden Source** — the stable Hindi input PDF (never regenerated)
2. **Golden Target** — a versioned JSON reference of expected English output (frozen, updated only on legitimate improvement)
3. **Candidate** — actual pipeline output compared against golden target

The gate runs 5 sub-checks: structural match, content completeness (±30% word count per chapter), script hygiene (Devanagari < 2% in body), glossary integrity (required terms + min entry count), and page count regression (≤1.5×).

**Rationale:**
- Word count tolerance of ±30% balances sensitivity (catches missing/duplicate content) with flexibility (translation naturally varies)
- Script hygiene threshold of 2% allows inline preserved terms in parentheses while catching untranslated passages
- Golden target is JSON (not PDF) for easy diffing, versioning, and test assertion
- Gate uses PyMuPDF for text extraction — consistent with existing visual regression tests

**Team Impact:**
- All squad members: golden-target.json must be updated when pipeline output legitimately changes
- Chani: changes to translation/export logic may require golden target updates
- Runner now has 6 gates total (golden QA runs last)


---

### Decision: Gate 6 Validated — Golden-Targeted QA Baseline Established

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  

Ran the full 6-gate quality validation against the current pipeline output (Test_Hindi_Book_final.pdf, 207.8KB, 14 pages). Gate 6 (golden-targeted QA) compares the candidate PDF against `tests/golden/golden-target.json`.

**Decision:** The current output passes all 6 gates and establishes the golden QA baseline. Gate 6 validates:
- Structural match: 9 chapters in correct order
- Content completeness: word counts within ±30% per chapter
- Script hygiene: 0% Devanagari in English body
- Glossary integrity: 14/14 required terms, 46 entries (min 35)
- Page count: 14 pages (within 1.5× of 10-page source)

**Team Impact:**
- **Thufir:** 43 regression tests + 38 gate unit tests all pass. The golden baseline is locked.
- **All:** Any future pipeline changes must pass Gate 6. If output legitimately improves, update golden-target.json — never auto-regenerate it.
- **Chani:** Gates 1–5 require stage output objects (need Azure DB). Gate 6 runs standalone with just the PDF path — useful for local CI.

---

### Decision: Golden Target English PDF as QA Benchmark Artifact

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  

Manish's Golden-Targeted QA spec requires three artifacts: Golden Source (Hindi PDF), Golden Target (English PDF), and Candidate Output (Pipeline PDF). The Golden Target English PDF was missing.

**Decision:**
- Created `tests/golden/golden-target-english.pdf` as a stable, checked-in visual benchmark.
- Generated by `scripts/generate_golden_target_pdf.py` using WeasyPrint (same CSS patterns as pipeline export).
- Contains cover + TOC + 9 chapters with scholarly English content matching `golden-target.json` structure.
- Intentionally omits Translator's Foreword and Glossary (those are pipeline-added features, not source content).
- Added `.gitignore` exception (`!tests/golden/golden-target-english.pdf`) since `*.pdf` is globally ignored.
- Gate 6 was NOT modified — it validates against the JSON data, not the PDF. The PDF serves as a human-readable visual/structural benchmark.

**Team Impact:**
- **Thufir:** Regression tests can now reference the golden target PDF for visual comparison.
- **All:** Three-artifact QA workflow is complete. Never regenerate the PDF automatically — update only when pipeline legitimately improves.

---

### Decision: ToC Page Numbers via target-counter() + Full Chapter Headings

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  
**Issue:** #14

## Context

Golden Target PDF and pipeline output both lacked ToC page numbers. Pipeline chapter headings were truncated at em-dash due to non-greedy regex in `_extract_chapter_title()`.

**Decision:**
1. **ToC page numbers** use WeasyPrint's `target-counter(attr(href url), page)` CSS function with `<a href="#chapter-N">` anchor links. This is applied in both the golden target script and the pipeline export.
2. **Chapter headings** now include the full title including em-dash subtitles (e.g., "Chapter 1: Dharma and Karma — The Message of the Gita" instead of just "Chapter 1: Dharma and Karma").
3. **Chapter anchor IDs** (`id="chapter-N"`) are added to all `<h1>` tags in both assembled HTML and golden target HTML to support ToC cross-referencing.

**Team Impact:**
- **Chani (Pipeline):** `assemble.py` and `export.py` now produce full chapter headings and page-numbered ToC.
- **Thufir (Testing):** `golden-target.json` word counts and `full_title` fields updated. All 76 regression tests pass.
- **Golden Target:** PDF regenerated with ToC page numbers. Stable artifact — do not regenerate automatically.

**Key Files:**
- `scripts/generate_golden_target_pdf.py` — golden target generator
- `src/transpose/pipeline/assemble.py` — `_extract_chapter_title()` fix
- `src/transpose/pipeline/export.py` — ToC `target-counter()` CSS
- `tests/golden/golden-target.json` — updated word counts and full_titles
- `tests/golden/golden-target-english.pdf` — regenerated

---

### Decision: Golden Target Self-Validation in Gate 6

**Author:** Thufir  
**Date:** 2026-04-20  
**Status:** Active  
**Issue:** #14

## Context

Gate 6 (`golden_targeted_qa_gate`) compares candidate pipeline output against `golden-target.json` as the reference standard. If the golden target itself is corrupt (garbled Unicode, empty chapters, missing structure), Gate 6 silently passes bad candidates against a bad baseline.

**Decision:**

Gate 6 now **validates the golden target before using it**:

1. `validate_golden_target()` checks for U+FFFD replacement characters, empty titles, zero word counts, missing cover/ToC sections.
2. If validation fails, Gate 6 returns FAIL immediately with `golden_target_validation_errors` in details — no candidate comparison.
3. A standalone integrity test suite (`test_golden_target_integrity.py`) validates the golden target independently of gate logic.

**Team Impact:**
- **Chani:** When updating `golden-target.json`, the integrity tests catch corruption before it reaches CI. The gate refuses to use a bad reference.
- **Thufir:** Boundary tests now read golden values dynamically — no more hardcoded word counts drifting from the file.
- **All:** Any future golden target update that introduces garbled text or incomplete data will be caught immediately.

**Key Files:**
- `src/transpose/pipeline/gates.py` — `validate_golden_target()` function
- `tests/regression/test_golden_target_integrity.py` — 19 standalone tests
- `tests/regression/test_golden_targeted_qa.py` — 15 new gate tests

---

### Decision: Quality Gate Analysis — Production Readiness (P0/P1 Issues)

**Author:** Stilgar (Lead/Architect)  
**Date:** 2026-04-20  
**Status:** Findings Documented; Priority Fixes Queued  

Deep comparative quality review revealed **7 issues**: 3 P0 (blocking), 2 P1 (significant), 2 P2 (minor). Current gates validate structural presence but not content fidelity.

**P0 Issues (Blocking):**
1. **Chapter Titles Truncated** — All 9 chapter titles missing subtitles after em-dash. Example: "Chapter 1: Dharma and Karma — The Message of the Gita" becomes "Chapter 1: Dharma and Karma". Root cause: heading extraction strips text after dash or hits character limit during assembly/export.
2. **Cover Title Placeholder** — Cover uses filename placeholder ("Test Hindi Book") instead of translated source title ("Hindi Literature and Culture — Test Booklet"). Root cause: cover generation uses ingest filename or metadata field instead of OCR'd/translated title.
3. **Devanagari Garbled in Glossary** — Glossary contains Unicode substitution artifacts (T, Ȩõ, ȫè replacing Devanagari codepoints). Examples: `आयुTर्वेद` (should be `आयुर्वेद`), `भȫèक्ति` (should be `भक्ति`). Root cause: font embedding or PDF export uses font lacking Devanagari conjuncts; WeasyPrint substitutes missing glyphs with Latin-extended artifacts.

**P1 Issues (Significant):**
4. **Key Phrases Missing** — Four chapters missing context phrases that exist in Hindi source and golden reference. Ch2: "spiritual discipline", "eight limbs"; Ch4: "fruits of action"; Ch8: "guru tradition", "meditation"; Ch9: "continuity". Root cause: translation stage summarizes aggressively or loses content during chunking.
5. **Word Count Inflation** — Output 60% larger than source (1.60× ratio) vs golden target at 1.05× (threshold: 1.50×). Ch9 shows 718 words output vs ~178 expected. Root cause: content from Translator's Foreword bleeds into Ch9 text stream; HTML/CSS layout doesn't properly separate boundaries.

**P2 Issues (Minor):**
6. **ToC Missing Page Numbers** — Golden target ToC includes page numbers; pipeline output doesn't. Impact: minor for digital; expected for print-ready.
7. **Golden JSON Incomplete** — Sections arrays empty (no sub-heading/paragraph-level validation possible). No cover title field. No Devanagari rendering validation criteria.

**What Existing Gates Miss:**
- Gate 6 validates chapter count (present?), word count (within ratio?), Devanagari density (>2%?), glossary terms (present?). Passes all checks above because body content is correct — only presentation/assembly is broken.
- No comparison of chapter title against `full_title` in golden JSON.
- No cover page title validation (just `has_title=true`).
- No Devanagari rendering integrity (PDF output validation, not data validation).
- No key phrase content coverage verification.
- No per-chapter word count validation (only total ratio).
- No ToC completeness check.

**Recommended New Gates:**
1. **Title Fidelity Gate** — Extract chapter headings from output PDF, compare against golden JSON `full_title` using fuzzy match (≥90%). Catches P0-1.
2. **Cover Page Validation Gate** — Compare cover title text against translated source title; reject filenames. Catches P0-2.
3. **Devanagari Rendering Integrity Gate** — Validate all Devanagari text in PDF output; flag U+0900–U+097F violations and Latin-extended artifacts. Catches P0-3.
4. **Key Phrase Coverage Gate** — Each chapter must contain all `key_phrases` from golden JSON (case-insensitive substring). Catches P1-1.
5. **Per-Chapter Word Count Gate** — Validate each chapter against golden JSON `word_count_approx` with tolerance. Catches P1-2 (Ch9 at 4× expected).
6. **ToC Completeness Gate** — Validate ToC includes page numbers and full chapter titles matching body headers. Catches P2-1.

**Priority Fixes:**
1. P0-3 (Devanagari rendering) — font/encoding in WeasyPrint export
2. P0-1 (Chapter titles) — heading extraction preserves full title including subtitle
3. P0-2 (Cover title) — use translated source title, not filename
4. P1-2 (Word inflation) — investigate Ch9 content bleed, fix layout boundaries
5. P1-1 (Key phrases) — may resolve with title fix; verify after

**Verdict:** NOT production-ready. Translation quality of body text is solid. Presentation layer (PDF assembly + export) is the blocker.

**Files:**
- `.squad/decisions/inbox/stilgar-qa-findings.md` — Full comparative review with examples

---

### Decision: Add Production Readiness Test Suite

**Author:** Thufir (QA/Testing)  
**Date:** 2026-04-20  
**Status:** Proposed  

Current pipeline gate (Gate 6) validates structural presence but not content quality. Built `tests/regression/test_production_readiness.py` with 61 tests across 8 dimensions as a **release-blocking** (not pipeline-blocking) regression suite.

**Test Coverage:**
- **Title Fidelity** — All chapter full titles match golden JSON (fuzzy ≥90%)
- **Cover Validation** — Cover title translated (not filename)
- **Devanagari Rendering** — No garbled Unicode in glossary/text (U+FFFD, Latin artifacts)
- **Key Phrase Coverage** — All `key_phrases` present in chapters
- **Word Count Ratio** — Per-chapter validation against `word_count_approx`
- **ToC Completeness** — Page numbers, full titles, consistency with body
- **Structural Integrity** — No broken content blocks, all chapters present
- **Artifact Validation** — All outputs exist, readable, no corruption

**Test Status:**
- 56 tests pass ✅
- 5 tests correctly fail on truncation bug (P0-1)
  - Chapter 1 full title missing
  - Chapter 3 full title missing
  - Chapter 5 full title missing
  - Chapter 9 full title missing
  - Glossary Devanagari validation

**Recommendation:**
- Tests should run in CI with `@pytest.mark.production` marker
- Release gating: `pytest -m production` must pass (not pipeline gate)
- Different cadence: Gate 6 runs on every pipeline execution; production tests run pre-release
- Once P0 issues fixed, all 61 tests should pass

**Key Files:**
- `tests/regression/test_production_readiness.py` — 61 tests, 8 test classes

---

### Decision: Docs-Update Convention

**Author:** Stilgar (Lead/Architect)  
**Date:** 2026-04-21  
**Status:** Active  

Four documentation files drifted significantly from the actual codebase. The Redis removal (commit 7b2b83d, serverless pivot), quality gates system, HTTP API, service context, unicode utilities, and many new test files were all added without corresponding doc updates. This created a state where architecture.md described a Redis dependency that no longer exists, project-structure.md listed files that don't exist and omitted files that do, and api-contracts.md had no mention of the gate system that blocks every stage transition.

**Enforce:** Any agent that adds, removes, or renames a source file or feature MUST update the corresponding documentation file in the same commit.

Specifically:
1. Adding/removing a source file → update `docs/project-structure.md`
2. Changing a pipeline stage contract → update `docs/api-contracts.md`
3. Adding/removing an Azure service dependency → update `docs/architecture.md` (service table + relevant sections)
4. Adding/removing a major feature (gates, API endpoints, utilities) → update `docs/architecture.md` and `README.md`
5. Adding/removing test files → update `docs/project-structure.md`

PR reviewers should check that doc files are included in any PR that touches the source tree structure or introduces a new feature. Docs stay current without periodic "catch-up" sprints; new team members can trust the docs as ground truth.

---

### Decision: Visual Quality Inspection — Round 2 (Devanagari Font Fix Required)

**Author:** Stilgar (Lead)  
**Date:** 2026-04-20  
**Status:** Blocker Identified  

Deep comparative quality review of `tests/fixtures/test-hindi-10page.pdf` → `Test_Hindi_Book_final.pdf` against `tests/golden/golden-target.json` revealed **1 P0 blocker, 2 P1 issues, 2 P2 minor issues**.

**Verdict: Conditional PASS** — Pipeline output substantially improved. All 3 prior P0s resolved (chapter titles now complete with subtitles, cover shows proper translated title, no wholesale garbling). One P0 remains: glossary Devanagari rendering has significant garbling (17 of 49 entries corrupted due to font embedding failure in WeasyPrint).

**P0 Blocker:**
- **Glossary Devanagari Garbling** — Character `9` replaces `व` (va); characters `ɜ·`, `ɡ`, `ɟ`, `ɠ`, `ɥÊ` replace vowel matras. Examples: `आयु9र्वेद` (should be `आयुर्वेद`), `भɜ·क्ति` (should be `भक्ति`). Font embedding issue in WeasyPrint PDF export.

**P1 Issues:**
- ToC page numbers all show "1" (non-functional navigation)
- dharma/karma Devanagari halant misordering (`धर्म` renders as `धमर्म`)

**P2 Issues:**
- Page count 15 vs golden 14 (extra glossary page)
- "sangat" Devanagari wrong (`संगक्ति` instead of `संगत`)

**Recommendations:**
1. Switch to Noto Sans Devanagari (comprehensive glyph coverage), ensure proper `@font-face` embedding
2. Add Devanagari rendering check to quality gates (flag U+0250–U+02AF IPA artifacts)
3. Generate ToC page numbers programmatically post-PDF or use two-pass approach
4. Verify glossary source data has correct Unicode sequences (NFC normalization)

**What IS Production-Ready:** Cover title correct, all 9 chapter titles complete with subtitles, content complete (no bleed/duplicates), word count ratios within tolerance (0.91x–1.16x), body script hygiene (Devanagari < 0.1%), Translator's Foreword well-crafted.

**Files:** Full analysis in `.squad/decisions/inbox/stilgar-visual-inspection-r2.md` (archived).

---
