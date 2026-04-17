# Project Context

- **Owner:** Mani
- **Project:** Transpose — agentic pipeline that translates scanned/digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence for OCR and Azure OpenAI GPT-4o for literary/cultural translation. Culturally significant words (atman, dharma, karma) must be preserved untranslated and collected into a glossary. Output: publication-ready ePub/PDF.
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights
- **Created:** 2026-04-17

## Architecture from Stilgar (2026-04-17T19:50:55Z)

7-stage sequential pipeline with strict input/output contracts (see `docs/api-contracts.md`). Each stage is independent Python module. Communication through PostgreSQL (persistent) + Redis (cache/orchestration). All stages idempotent. Services wrap Azure SDKs — pipeline never calls Azure directly (DocumentIntelligenceService, TranslationService, GlossaryService, StorageService in `src/transpose/services/`). Managed Identity everywhere. Seed glossary (~60 known cultural terms) + LLM detection for unknown. ePub-first, PDF rendered from same HTML.

**Your infrastructure must support:**
- PostgreSQL Flexible Server (persistent pipeline state, book metadata, translation records)
- Redis (ephemeral orchestration, cache) — losing Redis loses nothing permanent
- Azure Document Intelligence (OCR)
- Azure OpenAI GPT-4o (translation + cultural term detection)
- Azure Storage Blobs (source PDFs, output ePub/PDF)
- Azure Container Apps (run pipeline stages)
- Application Insights (observability)
- **All with Managed Identity** — zero secrets in code or environment

**Key files:** `docs/architecture.md`, `pyproject.toml`, `src/transpose/config/`, `src/transpose/services/`

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
