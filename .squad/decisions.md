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

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
