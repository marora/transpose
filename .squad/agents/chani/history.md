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
