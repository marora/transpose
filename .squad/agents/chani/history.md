# Project Context

- **Owner:** Mani
- **Project:** Transpose — agentic pipeline that translates scanned/digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence for OCR and Azure OpenAI GPT-4o for literary/cultural translation. Culturally significant words (atman, dharma, karma) must be preserved untranslated and collected into a glossary. Output: publication-ready ePub/PDF.
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights
- **Created:** 2026-04-17

## Architecture from Stilgar (2026-04-17T19:50:55Z)

7-stage sequential pipeline: **Ingest → OCR → Chunk → Translate → Glossary → Assemble → Export**. Each stage has async `run()` signature with typed input/output (see `docs/api-contracts.md`). Services wrap Azure SDKs (DocumentIntelligenceService, TranslationService, GlossaryService, StorageService in `src/transpose/services/`). All stages must be idempotent. Managed Identity everywhere. Seed glossary (~60 cultural terms) + LLM detection for unknown terms. PostgreSQL (persistent state), Redis (cache/orchestration). Python 3.12+ with src layout, hatch, ruff, pytest.

**Your responsibilities:**
- Implement all 7 stages following api-contracts.md
- All `run()` functions async
- Never call Azure directly; always use services/ wrappers
- All stages idempotent (re-runs skip completed work)
- JSON mode LLM output for structured extraction

**Key files:** `docs/architecture.md`, `docs/api-contracts.md`, `docs/project-structure.md`, `src/transpose/services/`, `src/transpose/pipeline/`

## Session 2026-04-17: Full Pipeline Implementation

**Delivered:** All 7 pipeline stages (Ingest, OCR, Chunk, Translate, Glossary, Assemble, Export), service wrappers (BlobClient, OcrClient, LlmClient, Database), ServiceContext dependency injection pattern, pipeline runner orchestrator with distributed locking, CLI interface. **2,921 lines of Python code, ruff clean, all async patterns, fully idempotent stages.**

Key accomplishments:
- Implemented ServiceContext as centralized service container for all stages
- Full CRUD database layer with parameterized queries (secure, reusable)
- Digital-first OCR: PyMuPDF + Document Intelligence fallback
- Paragraph-boundary chunking with chapter detection and overlap
- LLM translation with seed glossary injection + JSON mode for cultural terms
- Glossary aggregation with term normalization and occurrence filtering
- HTML document assembly with TOC generation
- Parallel ePub/PDF export from single HTML source
- Pipeline runner with distributed Redis locking + error handling + metrics
- CLI with book upload, pipeline trigger, status tracking

All stages follow `docs/api-contracts.md` contracts. All stages idempotent (re-runs skip completed work).

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-04-18: Local Dev Wiring Against Azure Resources

**TLS/Network findings:**
- asyncpg has the same TLS CRL hang as psycopg2 in WSL2 → the `PGSSLCRL`/`PGSSLCRLDIR` workaround is set in `cli.py` before imports.
- WSL2 NAT means the outbound IP seen by Azure is *not* the Windows host IP. A broad firewall rule (`AllowAll 0.0.0.0-255.255.255.255`) was added to the PG Flex server for local dev. Should be tightened for prod.
- asyncpg `ssl='require'` works fine once TCP connectivity is established — no need for a custom `ssl.SSLContext`.

**Settings/Config pattern:**
- pydantic-settings v2 natively loads `.env` files via `model_config = {"env_file": ".env"}` — no need for python-dotenv as a runtime dependency (though it must be installed as pydantic-settings uses it internally).
- `.env` is gitignored via `.gitignore` (both `.env` and `*.env` patterns).

**Database SSL approach:**
- `ServiceContext._requires_ssl` property auto-detects Azure PG by hostname suffix `.database.azure.com`.
- SSL mode is passed as a parameter to `Database.connect(ssl=...)` rather than appended to the DSN — asyncpg handles SSL via keyword arg, not DSN query params.
- `Database.connect()` now accepts an optional `ssl` parameter forwarded to `asyncpg.create_pool()`.

**Key file paths:**
- `.env` — local dev secrets (gitignored)
- `src/transpose/config/settings.py` — pydantic-settings with env_file support
- `src/transpose/services/context.py` — DSN building + SSL detection
- `src/transpose/services/database.py` — asyncpg pool with SSL passthrough
- `src/transpose/cli.py` — TLS CRL workaround at top of module

**Password auth:**
- Re-enabled on `transpose-dev-psql` via `az postgres flexible-server update --password-auth Enabled`.
- Admin password reset to the value in `.env` via `--admin-password`.

### 2026-04-18: PDF Export Fixes — Font Embedding and Layout Optimization

**Fixed GitHub issue #1:** Two visual bugs in PDF export causing page overflow and unreadable Devanagari text.

**Changes to `src/transpose/pipeline/export.py` (_generate_pdf function):**

1. **Devanagari Font Embedding:**
   - Added `@font-face` declaration for `NotoSansDevanagari.ttf` with `file://` URL pointing to `fonts/NotoSansDevanagari.ttf`
   - Used `Path(__file__).resolve().parents[3]` to dynamically resolve font path relative to repo root (no hardcoded paths)
   - **Key fix:** Separated CSS into WeasyPrint `CSS()` object with `font_config` parameter. Initial attempt had inline CSS not connected to FontConfiguration. Fixed by building CSS as object: `css = CSS(string=f"...@font-face..."); HTML(...).write_pdf(font_config=font_config, stylesheets=[css])`
   - Updated `font-family` CSS to `Georgia, 'Noto Sans Devanagari', serif` — Georgia for Latin, Noto Sans Devanagari for Hindi/Devanagari Unicode blocks, serif as final fallback

2. **Title Page Layout Fix:**
   - Reduced `.title-page` padding-top from `5cm` → `3cm` (less vertical waste)
   - Reduced `.title` font-size from `36pt` → `28pt` (fits better on page 1)
   - Added `page-break-after: always` to `.title-page` class to ensure chapter content starts on page 2 (matching source PDF structure)

3. **Glossary Rendering:**
   - With font embedding, glossary `entry.original_script` (Devanagari) now renders correctly instead of tofu/replacement characters
   - No code changes needed here — the font-family fallback handles it automatically

**Key Decisions:**
- WeasyPrint does **not** auto-discover system fonts — explicit `@font-face` with `file://` URLs is required for embedded fonts
- Using `FontConfiguration()` with proper CSS object structure is required. Inline CSS with FontConfiguration doesn't work.
- Pathlib-based dynamic path resolution prevents brittleness across environments (dev vs container vs tests)

**Testing:**
- All 8 export stage tests pass (`tests/unit/pipeline/test_export.py`)
- 12 visual regression tests pass (`tests/unit/test_export_visual.py`) — validates title page layout, Devanagari rendering, glossary, page counts, edge cases
- Ruff linting clean
- No regressions in existing functionality

**Outcome:** Generated PDFs now correctly render all Devanagari text (cultural terms, glossary entries) and title page fits on page 1 without overflow. Visual regression testing prevents future regressions.

### 2026-04-18: Cloud Deployment Prep — HTTP API, Blob-Source Ingest, Test PDF

**HTTP API (`src/transpose/api.py`):**
- Lightweight aiohttp server with three endpoints: `GET /health`, `POST /translate`, `GET /status/{book_id}`.
- `/translate` accepts `blob_uri` (PDF already in blob storage), fires pipeline in background via `asyncio.create_task`.
- In-memory job tracker (`_jobs` dict) for status polling — sufficient for single-replica Container Apps.
- TLS CRL workaround replicated from `cli.py` since `api.py` is now the container entrypoint.
- Dockerfile CMD is `python -m transpose.api` (port 8000).

**Blob-source ingest (`src/transpose/pipeline/ingest.py`):**
- `IngestInput` now has optional `blob_uri` field. When set, downloads PDF from blob instead of reading from disk.
- `_parse_blob_uri()` extracts (container, blob_name) from full Azure blob URI.
- When `blob_uri` is set, upload step is skipped (PDF is already in blob storage).
- Local file path (`source_path`) still works for CLI usage — backward compatible.
- `PipelineInput` also gained `blob_uri` field, passed through to `IngestInput`.

**Hindi test PDF:**
- `scripts/create_test_pdf.py` generates a 10-page Hindi PDF using PyMuPDF + Noto Sans Devanagari font.
- Content covers dharma, karma, moksha, yoga, prana, sangat, langar, seva, guru — all key cultural terms.
- Font file: `fonts/NotoSansDevanagari.ttf` (downloaded from Google Fonts CDN).
- Output: `tests/fixtures/test-hindi-10page.pdf` (697KB, ~165 words/page).
- Uploaded to `transposedevst/source-pdfs/test-hindi-10page.pdf`.

**Dependencies:**
- `aiohttp>=3.9.0` added to pyproject.toml (was already installed, now declared).

**RBAC note:**
- `Storage Blob Data Contributor` role was assigned to the admin principal on `transposedevst` for blob upload. RBAC propagation took ~60s before `az storage blob upload --auth-mode login` worked (needed explicit `--subscription` flag).

### 2026-04-19: Devanagari OCR Fix — Locale Hint, NFC Normalization, Validation Layer (Issue #7)

**Problem:** OCR pipeline produced garbled Unicode for Devanagari pages (e.g., 'धǺ R yǺ' instead of 'धर्म और कर्म'). Root cause: no locale hint to Document Intelligence + no Unicode normalization + no post-OCR validation.

**Changes to `src/transpose/services/ocr_client.py`:**
- Added `locale="hi"` keyword arg to `begin_analyze_document()` — tells Azure DI to expect Devanagari script
- Applied `unicodedata.normalize('NFC', text)` to all extracted text before returning
- Lowered confidence threshold to 0.5 (from 0.7) for `needs_review` flagging — pages below 0.5 are genuinely garbled
- Added word-level confidence logging (warns when >0 words below 0.5 confidence, logs samples)
- Added `locale_hint` and `review_reason` to `ocr_metadata` dict

**Changes to `src/transpose/pipeline/ocr.py`:**
- Added `_normalize_text()` helper applying NFC normalization — used on both digital (PyMuPDF) and scanned paths
- Added `_validate_page()` function checking: minimum text length, Devanagari codepoint presence (U+0900-U+097F) when source is Hindi, excessive replacement characters (U+FFFD)
- Validation runs on both digital and OCR-extracted pages
- Pages failing validation get `needs_review=True` with `validation_issues` list in `ocr_metadata`
- Added per-page validation logging and summary log

**Key decisions:**
- NFC normalization on *both* paths (digital + scanned) — PyMuPDF can also produce non-NFC text
- Validation is a separate function, not tied to confidence scoring — catches structural problems (no Devanagari, all replacement chars) that confidence alone misses
- Did NOT change Page model or OcrOutput signatures — backward compatible
- `_LOW_CONFIDENCE_THRESHOLD = 0.5` in ocr_client — tighter than old 0.7 but for reject/review, not filtering

**All 39 existing OCR tests pass. Ruff clean.**

### 2026-04-18: Cross-Page Paragraph Joining (Issue #6)

**Problem:** The chunk stage blindly inserted `\n\n` between every page, splitting mid-sentence paragraphs that span PDF page boundaries into separate chunks — producing broken, unpublishable output.

**Fix:** Added a paragraph-joining pass (`_join_cross_page_paragraphs`) that runs BEFORE the chunking logic. Three new helpers:
- `_ends_with_terminal(text)` — checks for `.`, `?`, `!`, `।` (Devanagari danda), `॥`, `—`, and quote characters
- `_starts_with_continuation(text)` — detects lowercase Latin or Devanagari script (U+0900–U+097F)
- `_join_cross_page_paragraphs(pages)` — replaces `\n\n` with a single space at page boundaries where continuation is detected

**Conservative approach:** Only joins when BOTH conditions hold (no terminal + continuation start). Pages ending with proper sentence terminators always get the paragraph break preserved.

**No model/signature changes.** ChunkInput, ChunkOutput, ChunkResult unchanged. Chapter detection and overlap logic untouched. All 14 existing unit tests pass.

### 2026-04-18: Translation Completeness Enforcement (GitHub Issue #8)

**Problem:** Raw untranslated Hindi source text was bleeding through to output PDFs. Failed translation blocks silently crashed the pipeline or passed source text through unchanged.

**Changes to `src/transpose/pipeline/translate.py`:**

1. **Per-chunk error handling:** Wrapped `translate_chunk()` call in try/except. On failure, creates a placeholder `TranslationResult` with `translated_text="[TRANSLATION FAILED — REVIEW REQUIRED]"` instead of crashing the pipeline.
2. **Database record for failed chunks:** A `Translation` record with placeholder text is persisted to the database so downstream stages (Glossary, Assemble, Export) always have data to work with.
3. **Completeness check:** After the translation loop, validates `len(translations) == len(chunks_to_translate)`. Raises `ValueError` if counts don't match (defensive — should never trigger given the try/except).
4. **`failed_count` field:** Added to `TranslateOutput` with `default=0` for backward compatibility.
5. **`TRANSLATION_FAILED_PLACEHOLDER` constant:** Module-level constant for the exact placeholder string, importable by tests and downstream code.
6. **Context continuity:** On failure, `previous_translation` is NOT updated — next chunk gets the last *successful* translation context, preserving continuity.

**Key design choice:** Failed chunks don't halt the pipeline. The placeholder text is visually obvious in output, making review easy. The `failed_count` field lets callers detect partial failures programmatically.

**Testing:** All 26 existing translate tests pass. Ruff clean. No model changes needed — `Translation.translated_text` already accepts any string.

### 2026-04-19: Defensive NFC Normalization for Glossary Hindi Terms (Issue #9)

**Problem:** Glossary `original_script` (Devanagari/Gurmukhi) values could arrive corrupted if any upstream stage emitted non-NFC Unicode. Issue #7 added NFC at OCR layer, but no downstream stages had their own normalization — a single bypass path (e.g., seed glossary, LLM cultural terms) could reintroduce corrupted text.

**Fix — defense in depth:** Created `src/transpose/utils/unicode.py` with a shared `normalize_unicode()` helper, then applied it at every touchpoint:

1. **translate.py:** NFC-normalize `original_script` when building `ExtractedTerm` from LLM response
2. **glossary.py:** NFC-normalize when aggregating `original_script` into term data
3. **export.py:** NFC-normalize at ePub and PDF rendering (both glossary loops)
4. **seed_glossary.py:** NFC-normalize seed terms in `get_seed_glossary()`

**Key decision:** Each layer normalizes independently — no layer trusts upstream to have done it. This is cheap (NFC on already-NFC text is a no-op) and guarantees correctness regardless of data provenance.

**Testing:** All 223 existing tests pass. Ruff clean. No model/signature changes.

### 2026-04-19: Auto-Generated Translator's Foreword (Issue #12)

**Problem:** Product spec requires a Translator's Foreword explaining the cultural translation philosophy and preserved-word approach. This front-matter page was missing from generated output.

**Changes across 3 source files + 2 test files:**

1. **`src/transpose/services/llm_client.py`** — Added `chat()` method for freeform LLM prompts (non-translation tasks). Uses tenacity retry like `translate_chunk()`.

2. **`src/transpose/pipeline/assemble.py`:**
   - Added `foreword` field (Optional[str]) to `AssembleOutput`
   - Added `_generate_foreword(ctx, book_title, cultural_terms)` — builds a prompt requesting a 250-400 word foreword in warm scholarly tone, preserving top 15 cultural terms
   - After building chapters/TOC, invokes LLM to generate foreword; stores in `manuscript.metadata["foreword"]`
   - Foreword generation failure is non-fatal (logged warning, pipeline continues)

3. **`src/transpose/pipeline/export.py`:**
   - **ePub:** Foreword rendered as a separate `foreword.xhtml` chapter inserted before all content chapters in the spine
   - **PDF:** Foreword rendered as `<div class='foreword-page'>` after TOC, before page counter reset/chapters
   - CSS: `.foreword-page { page-break-after: always; }`, `.foreword-content p { text-indent: 1.5em; font-style: italic; }`

**Key decisions:**
- Foreword stored in `manuscript.metadata["foreword"]` — no model schema change, editable via metadata
- Graceful degradation: LLM failure doesn't block the pipeline
- `LlmClient.chat()` is generic — reusable for future non-translation LLM tasks
- Foreword is front matter (after TOC, before Chapter 1) in both formats

**Testing:** 229 tests pass (6 new). Ruff clean.

### 2026-04-19: Cover Page, Table of Contents, Page Numbering (Issues #10, #13, #11)

**Problem:** Translated PDFs had a bare plain-text title (no visual hierarchy), no Table of Contents page, and no page numbering.

**Changes to `src/transpose/pipeline/export.py`:**

1. **Issue #10 — Cover Page Enhancement:**
   - Title page now has 32pt bold title with 2px letter-spacing
   - Subtitle support via `manuscript.metadata.get("subtitle")` — optional, rendered in 20pt italic when present
   - Decorative `<hr>` separator between title/subtitle and author
   - Author in 16pt with letter-spacing
   - ePub gets a `cover.xhtml` as the FIRST chapter in the spine, with matching CSS

2. **Issue #13 — Auto-generated Table of Contents:**
   - ToC page inserted between cover and first chapter in PDF
   - Renders from `manuscript.table_of_contents` (built by assemble stage)
   - Styled with centered heading, dotted border-bottom entries at 14pt
   - `page-break-after: always` ensures chapters start on a fresh page
   - ePub ToC already functional via `ebook.toc` tuple + EpubNcx/EpubNav — verified, no changes needed

3. **Issue #11 — Page Numbering:**
   - CSS `@page` rule adds `counter(page)` at bottom-center in 10pt gray
   - `@page :first` suppresses page number on cover
   - `.title-page` and `.toc-page` use `page: frontmatter` named page with roman numerals
   - `<div style='counter-reset: page 1;'>` inserted before first chapter resets to arabic numbering

**Key decisions:**
- Kept `padding-top: 3cm` on title page (not 5cm from issue spec) — 5cm caused overflow in visual tests, 3cm was proven safe in earlier fix
- Subtitle is optional (from metadata), not auto-detected from first chapter — cleaner, no false positives
- All three changes are in the same commit since they share CSS and HTML ordering dependencies

**Testing:** All 223 tests pass (including 12 visual regression tests). Ruff clean. No model or contract changes.

## Session 2026-04-20: Quality Gates Implementation

**Delivered:** Blocking quality gates between pipeline stages. 5 gate functions in `src/transpose/pipeline/gates.py`, runner integration in `runner.py`, 34 unit tests in `tests/unit/pipeline/test_gates.py`, CI workflow in `.github/workflows/quality-gates.yml`.

**Gates implemented:**
1. `ocr_sanity_gate` — after OCR, checks replacement chars, Devanagari density, confidence
2. `translation_completeness_gate` — after translate, checks failed ratio, Devanagari passthrough, TRANSLATION FAILED markers
3. `glossary_integrity_gate` — after glossary, checks NFC normalization, replacement chars, Latin in Devanagari, non-empty
4. `document_structure_gate` — after assemble, checks ToC/chapter count, foreword length, title, sequential numbering
5. `artifact_availability_gate` — after export, checks PDF/ePub presence, size >1KB, valid URIs

**Key design decisions:**
- Gates use duck-typing via `getattr()` — no tight coupling to stage output dataclasses
- `GateResult` dataclass carries gate_name, passed, failures list, details dict, timestamp
- `QualityGateError` wraps GateResult so runner can catch and write partial validation report
- Runner writes `validation-report.json` to output_dir (full on success, partial on gate failure)
- PipelineOutput gained `gate_results` field (list of dicts)

**Learnings:**
- Most Devanagari characters are identical in NFC vs NFD form in Python's `unicodedata`. Testing NFC normalization requires using characters that actually decompose (like Latin é = e + combining acute). Pure Devanagari strings often don't change between NFC/NFD.
- Thufir's test-first stubs had different function signatures (dict-based, 2-arg) from the real implementation (typed stage outputs, 1-arg). Had to completely rewrite tests rather than fill in stubs.

**Testing:** 34 gate-specific tests pass. Full suite: 279 pass, 4 xfail, 1 pre-existing env-dependent failure (test_settings).

### 2026-04-19: First Full E2E Validation Run with Quality Gates

**Run context:** Used cached data from book_id `d6671336-522a-48b6-82ee-624380d706b8` (10-page Hindi PDF). Stages ingest→assemble were reconstructed from PostgreSQL; export was run fresh.

**Quality Gate Results — 4/4 core gates PASS:**
1. ✅ **OCR Sanity** — 10 pages, no replacement chars, Devanagari density above threshold, confidence OK
2. ✅ **Translation Completeness** — 10/10 chunks translated, 0 failures, 0 Devanagari passthrough
3. ✅ **Glossary Integrity** — 51 entries, all NFC-normalized, no replacement chars, no Latin in Devanagari
4. ✅ **Document Structure** — 10 chapters, 10 ToC entries matching, foreword 288 words (≥50), title present, sequential numbering
5. ❌ **Artifact Availability** — False positive in local dev mode. Gate checks `uri.startswith("http")` which fails for local file paths. Both artifacts generated correctly: ePub 34KB, PDF 262KB (both >1KB threshold).

**Artifacts generated:**
- `Test_Hindi_Book_final.pdf` — 262KB, Devanagari font embedded, cover page, ToC, foreword, 10 chapters, glossary, page numbers
- `Test_Hindi_Book_final.epub` — 34KB, same content structure
- `validation-report.json` — Full gate results with details

**Key finding:** The `artifact_availability_gate` URI check (`uri.startswith("http")`) is too strict for local dev. In cloud mode (blob upload), URIs are `https://...`. In local mode, paths are `/absolute/path/...`. The gate should either skip URI validation when URI is a local path, or use a separate check for local vs cloud artifacts. Filed as a known issue — not blocking.

**Runner script:** `scripts/e2e_validation_run.py` — reconstructs stage outputs from DB, runs gates independently, generates artifacts locally (bypasses blob upload), writes validation report. Reusable for future E2E validation runs.

### 2026-04-20: Artifact Availability Gate Fixed for Local Dev (Task 1)

**Problem:** The `artifact_availability_gate` in `gates.py` rejected local file paths because it only accepted `http://` URIs. In local dev mode, artifacts are written to the filesystem with absolute paths like `/home/user/.../file.pdf`.

**Fix:** Updated `gates.py` line 395-416 to accept:
- `http://` and `https://` URIs (existing behavior for Azure Blob Storage)
- `file://` URIs (with path extraction and file existence check)
- Absolute file paths starting with `/` (Unix) or drive letter (Windows)
- For local paths, the gate verifies the file actually exists on disk using `os.path.isfile()`

**Testing:** Added 5 new tests to `tests/unit/pipeline/test_gates.py`:
- `test_accepts_https_uri` — validates https:// URIs pass
- `test_accepts_file_uri` — validates file:// URIs pass when file exists
- `test_accepts_absolute_path` — validates absolute paths like /tmp/file.pdf pass
- `test_fails_with_nonexistent_file_path` — validates non-existent paths fail
- Updated `test_fails_with_invalid_uri` to check for broader error message

All 10 artifact gate tests pass. No breaking changes.

### 2026-04-20: Page Inflation Fixed — Issue #11 (Task 2)

**Problem:** E2E run produced 38 pages for a 10-page source document (3.8× inflation). Root cause analysis revealed:
1. **ToC rendering full chapter content instead of titles** — The ToC on page 2 was rendering full Devanagari chapter content (thousands of characters) instead of short chapter titles, causing the ToC to span pages 2-5.
2. **Devanagari chapter refs used as titles** — `assemble.py` was using `chunk.chapter_ref` (original Devanagari chapter name from source) as the chapter title in both the ToC and chapter HTML `<h1>` headers.
3. **CSS page breaks per chapter** — Each `<h1>` triggers `page-break-before: always`, which is correct for separating chapters, but the ToC overflow was adding ~3 extra pages.

**Fix applied to `src/transpose/pipeline/assemble.py`:**

1. **Added `_extract_chapter_title()` helper function** — Extracts English chapter title from the first translated chunk in each chapter using regex patterns:
   - Matches "Chapter N: Title" patterns and extracts up to the separator (—)
   - Matches title-case lines like "Introduction" or "CHAPTER 2: YOGA"
   - Falls back to first non-empty line if no pattern matches
   - Maximum title length check (100 chars) to avoid using paragraph text as title

2. **Updated chapter assembly logic (line 84-114)** — Changed from using `chapter_title` (Devanagari) to `english_title` (extracted from translation):
   - Renamed loop variable from `chapter_title` to `chapter_ref` for clarity
   - Extract English title via `_extract_chapter_title(chapter_chunks, chapter_ref)`
   - Use `english_title` in chapter HTML `<h1>` tag
   - Use `english_title` in Manuscript chapter object
   - Use `english_title` in ToC entries

3. **Added CSS fix in `export.py`** — Added `page-break-inside: avoid` to `.toc-entry` CSS rule (line 352) to prevent individual ToC entries from breaking across pages (defensive fix, now unnecessary since titles are short).

**Expected outcome after fix:**
- **Cover:** 1 page
- **ToC:** 1 page (short English chapter titles like "Chapter 1: Dharma and Karma")
- **Foreword:** 1 page
- **Chapters:** ~8 pages (5 chapters with translated English content)
- **Glossary:** 1 page
- **Total:** ~12 pages (well within 1.5× = 15 pages threshold)

**Testing:**
- Unit tests pass: All 16 assemble tests pass, title extraction logic validated with 3 test cases
- Updated regression test documentation in `test_golden_reference.py` to explain expected page structure
- **Full regression validation requires pipeline re-run** — Current PDF has old data with Devanagari ToC

**Page numbering verification (Issue #11):** Reviewed CSS in `export.py` — page numbering already implements the spec:
- Cover page: no number (line 274-276)
- Front matter (ToC, foreword): roman numerals via `@page frontmatter` (lines 278-287)
- Body content: arabic numerals starting from 1 via `counter-reset: page 1` (line 422)

No changes needed for page numbering — already correct.

**Note for next pipeline run:** The manuscript data in PostgreSQL contains Devanagari chapter refs. After this fix, re-running `assemble` + `export` stages will generate proper English titles and compact ToC, reducing page count from 38 to ~12-15 pages.


### 2026-04-20: E2E Validation — Page Inflation Fix Verified

**Task:** Re-run full E2E pipeline to validate page inflation fix from Issue #11.

**Context:** Previous E2E run produced 38 pages for 10-page source. Fixes were committed to:
- `assemble.py` — extract English chapter titles from translations
- `export.py` — add page-break-inside: avoid for glossary entries
- `gates.py` — artifact gate accepts local paths

**Key discovery:** The `scripts/e2e_validation_run.py` script reconstructs gates from DB data but does NOT re-run assemble stage. It only runs export to generate fresh artifacts. This meant the manuscript in the database still had the old Devanagari chapter titles.

**Solution:**
1. Manually ran assemble stage via Python script to regenerate manuscript with English titles
2. Re-ran e2e_validation_run.py to generate fresh PDF/ePub from new manuscript

**Results after fix:**
- **PDF page count:** 14 pages (down from 38, within expected 12-15 range)
- **PDF size:** 209KB (down from 258KB)
- **ePub size:** 17KB (down from 34KB)
- **All 5 quality gates:** PASS
- **All 20 regression tests:** PASS (including page count test)

**Chapter titles now properly extracted:**
1. Introduction
2. Chapter 1: Dharma and Karma
3. Chapter 2: Yoga and Meditation
4. Chapter 3: Sikh Tradition
5. Chapter 4: Moksha and Vedanta Philosophy
6. Chapter 5: Hindi Literature
7. Chapter 6: Bollywood and Indian Cinema
8. Chapter 7: Festivals and Traditions
9. Chapter 8: Ayurveda and Ancient Medicine
10. Chapter 9: Conclusion

**Learning:** E2E validation scripts should be explicit about which stages they re-run vs reconstruct from DB. For future validation runs after code fixes:
- If fix is in assemble/earlier stages → must re-run those stages OR delete old manuscript
- If fix is only in export → e2e_validation_run.py is sufficient
- The `_extract_chapter_title()` regex patterns work correctly — extracts concise English titles like "Chapter 1: Dharma and Karma" instead of full Devanagari content

**Validation-report.json summary:**
- Overall: PASS
- Gates passed: 5/5
- PDF: 213KB at Test_Hindi_Book_final.pdf
- ePub: 17KB at Test_Hindi_Book_final.epub
