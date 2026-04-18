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

Transpose uses a 7-stage sequential pipeline: Ingest → OCR → Chunk → Translate → Glossary → Assemble → Export. Each stage is an independent Python module with typed input/output contracts. Stages communicate through PostgreSQL (source of truth) and Redis (orchestration/cache).

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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
