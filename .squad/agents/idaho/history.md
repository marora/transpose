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

## Session 2026-04-17: Complete Cloud Infrastructure

**Delivered:** 8 modular Bicep modules (Container Apps, PostgreSQL Flexible Server, Redis, Storage, Key Vault, Cognitive Services, Monitoring, Identity), Dockerfile with multi-stage build for Python 3.12, docker-compose.yml for local dev, database migration script (init-db.sql), comprehensive deployment docs. **1,220 lines of infrastructure code.**

Key accomplishments:
- PostgreSQL Flexible Server with Entra-only authentication (no passwords ever)
- Redis Basic tier for cache/orchestration state
- Container Apps with Managed Identity for all Azure service auth
- 8 RBAC role assignments ensuring least-privilege access
- Blob Storage with versioning and soft-delete for data safety
- Document Intelligence + Azure OpenAI GPT-4o with quota capacity sizing
- Application Insights + Log Analytics for observability
- Key Vault for Redis access key (only secret needed)
- Modular Bicep design with dependency chaining and output parameters
- Docker setup with WeasyPrint system dependencies, health probes
- Production readiness checklist with VNet/Private Endpoints/NSGs roadmap

All resources provisioned with Managed Identity — zero secrets in code or environment (except Redis password via Key Vault reference).

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->
