# Squad Decisions

## Active Decisions

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
