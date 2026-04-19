# Project Context

- **Owner:** Mani
- **Project:** Transpose — agentic pipeline that translates scanned/digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence for OCR and Azure OpenAI GPT-4o for literary/cultural translation. Culturally significant words (atman, dharma, karma) must be preserved untranslated and collected into a glossary. Output: publication-ready ePub/PDF.
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights
- **Created:** 2026-04-17

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2025-07-18 — Architecture Laid Down

- **7-stage pipeline:** Ingest → OCR → Chunk → Translate → Glossary → Assemble → Export
- **Contract pattern:** Each stage has `async def run(input: StageInput) -> StageOutput`. Stages never import each other.
- **Service wrapper pattern:** `src/transpose/services/` wraps all Azure SDKs. Pipeline stages never call SDKs directly.
- **Seed glossary:** ~60 curated cultural terms in `src/transpose/config/seed_glossary.py`. LLM detects more at translation time.
- **Idempotency is architectural.** Every stage skips already-completed work. This is enforced by unique constraints in the DB schema.
- **Key files:** `docs/architecture.md` (system design), `docs/api-contracts.md` (stage contracts), `pyproject.toml` (deps)
- **Tech choices:** Python 3.12+, hatch build system, ruff linter, pytest + pytest-asyncio, asyncpg, ebooklib + weasyprint for output
- **Auth:** Managed Identity everywhere. `DefaultAzureCredential` in all service wrappers. No secrets in code.
- **Observability:** OpenTelemetry traces + custom metrics defined in `src/transpose/observability/metrics.py`
- **DB:** PostgreSQL with UUID PKs, JSONB for flexible metadata, unique constraints for idempotency. Schema in `docs/architecture.md`.
- **Redis:** Pipeline status, progress, distributed locks, chunk cache. All ephemeral — losing Redis loses nothing permanent.

### 2025-07-18 — Governance Reset

- **Definition of Done is proof-based.** Nothing is "done" without generated artifacts (PDF + ePub), stable download links, a validation report, and all 5 quality gates passing. Claims without proof are open items.
- **5 blocking quality gates:** OCR Sanity → Translation Completeness → Glossary Integrity → Document Structure → Artifact Availability. Sequential, fail-fast. Each gate has specific pass/fail criteria and produces machine-readable JSON.
- **Quality ownership assigned:** Thufir owns gates (can block PRs), Idaho owns artifacts/publishing/observability/security. No shared ownership.
- **CI enforcement:** Every PR runs all gates. Bot posts artifact links + validation report + gate summary. Any failure blocks merge. JSON reports enable automation.
- **Governance files live in `.squad/quality/`:** `definition-of-done.md`, `gates.md`, `ownership.md`, `ci-gates.md`. Decision recorded in `.squad/decisions/inbox/stilgar-governance-reset.md`.
