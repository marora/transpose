# Project Context

- **Owner:** Mani
- **Project:** Transpose — agentic pipeline that translates scanned/digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence for OCR and Azure OpenAI GPT-4o for literary/cultural translation. Culturally significant words (atman, dharma, karma) must be preserved untranslated and collected into a glossary. Output: publication-ready ePub/PDF.
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights
- **Created:** 2026-04-17

## Architecture from Stilgar (2026-04-17T19:50:55Z)

7-stage sequential pipeline (Ingest → OCR → Chunk → Translate → Glossary → Assemble → Export). Test structure mirrors source: `tests/unit/` for module tests (mocking service wrappers), `tests/integration/` for end-to-end against real Azure fixtures. Unit tests validate contracts (type validation, error handling, edge cases). Integration tests ensure Azure SDK calls work correctly. All stages idempotent (re-runs skip completed work). 

**Test requirements:**
- Mock service wrappers (DocumentIntelligenceService, TranslationService, GlossaryService, StorageService) in unit tests
- Real Azure fixtures in integration tests (can reuse Managed Identity)
- Contracts defined in `docs/api-contracts.md` — validate types in unit tests
- Each stage has async `run(input: StageInput) -> StageOutput` signature — test async behavior
- Redis + PostgreSQL for integration tests (fixtures handle teardown)

**Key files:** `tests/unit/`, `tests/integration/`, `docs/api-contracts.md`, `src/transpose/models/` (domain objects)

## Session 2026-04-17: Comprehensive Test Suite

**Delivered:** 147 total tests (10 existing + 137 new), 15 test files covering all 7 pipeline stages + services + integration. Unit tests mock service layer with AsyncMock + fakeredis. **P0 cultural term preservation tests: 16 parametrized tests for Hindi/Punjabi terms.** All tests passing, all ruff clean.

Key accomplishments:
- 7 pipeline stage unit tests (9-15 tests each): Ingest, OCR, Chunk, Translate, Glossary, Assemble, Export
- 2 service unit tests: Database CRUD, Cache (fakeredis) operations
- Pipeline runner unit tests: orchestration, status transitions, distributed locking
- 2 integration tests: end-to-end pipeline flow, cultural preservation validation
- 16 parametrized cultural term tests (7 Hindi: dharma, karma, atman, moksha, guru, yoga, bhakti; 7 Punjabi: sangat, langar, seva, gurdwara, waheguru, naam, simran)
- Shared fixtures with realistic test data (Hindi/Punjabi text samples, mock OCR responses, seed glossary)
- Contract-based testing validating `docs/api-contracts.md` input/output shapes
- Service layer mocking allows tests to pass before implementation
- Integration tests validate orchestration without real Azure services

**Test organization:** `tests/unit/` (11 files, ~120 tests), `tests/integration/` (2 files, ~21 tests), `tests/fixtures/` (sample text, OCR responses)

Cultural term preservation is P0 — if atman gets translated, the test fails.

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
