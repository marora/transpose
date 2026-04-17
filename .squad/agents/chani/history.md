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
