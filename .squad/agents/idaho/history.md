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

### Session 2026-04-17: ACR + First Real Deployment

**Delivered:** Full deployment pipeline from code to running Container App.

- **ACR created:** `transposedevacr.azurecr.io` (Basic SKU, swedencentral). Name `transposedevacr` was available.
- **AcrPull role** assigned to `transpose-dev-identity` managed identity — no admin credentials needed.
- **Dockerfile fix:** `libgdk-pixbuf2.0-0` → `libgdk-pixbuf-2.0-0` on python:3.12-slim (Debian Bookworm). Also fixed `FROM ... as` → `FROM ... AS` for BuildKit compliance.
- **Image `transpose:v1`** built locally and pushed to ACR. Multi-stage build with WeasyPrint deps.
- **Container App updated:** `transpose-dev-app` now runs real code (not hello-world). All env vars configured including PostgreSQL, OpenAI, Doc Intelligence, Storage, Key Vault, App Insights connection string.
- **External ingress enabled** for testing. FQDN: `transpose-dev-app.yellowcoast-177ceb3f.swedencentral.azurecontainerapps.io`
- **Health endpoint verified:** `GET /health` returns `{"status": "ok", "service": "transpose"}`
- **ACR Bicep module** added at `infra/modules/acr.bicep` with AcrPull role assignment built in.
- **Note:** PostgreSQL password is set as plain env var for now. Should move to Key Vault reference in Phase 2.
- **Note:** Created minimal `src/transpose/api.py` with aiohttp for health/root endpoints. Chani will enhance with pipeline trigger endpoints.

### 2026: Documentation Sync

Updated `infra/README.md` Directory Structure section to include:
- `main.json` (compiled ARM template)
- `acr.bicep` module (Azure Container Registry)

Also updated "Last Updated" date from 2024 to 2026.

### 2026: Azure Monitor Workbook Dashboard

**Delivered:** Full observability dashboard and documentation overhaul.

- **Workbook template** (`infra/workbooks/transpose-dashboard.json`): 5-tab Azure Monitor Workbook covering Pipeline Overview, Translation Performance, OCR & Quality, Infrastructure Health, and Errors & Alerts. All KQL queries target `customMetrics`, `requests`, `dependencies`, `exceptions`, and `performanceCounters` tables. Parameterized with `TimeRange` and `AppInsightsResource` selectors.
- **Deploy script** (`infra/workbooks/deploy-workbook.sh`): Uses `az rest` PUT against the ARM API (`Microsoft.Insights/workbooks`) with a deterministic workbook GUID for idempotent re-deploys.
- **Observability docs** (`docs/observability.md`): Comprehensive guide covering 2026 Portal navigation (Investigate menu, not old Performance blade), all KQL queries, alert rule setup with thresholds, and troubleshooting runbooks (stuck pipeline, high latency, OOM, OCR garbage, DB connection failures).
- **Updated `infra/README.md`**: Replaced inline KQL snippets with pointer to `docs/observability.md` plus quick-start workbook import instructions.
- **Design decision:** Token cost estimation uses GPT-4o pricing ($2.50/1M input, $10.00/1M output). Workbook uses conditional visibility groups for tab navigation. Alert thresholds tuned for 75-page book workloads.

