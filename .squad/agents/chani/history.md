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

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
