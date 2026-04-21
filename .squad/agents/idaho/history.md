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

### Session 2026-04-20: Production Blocker Fix (B2, B3, B5)

**Committed:** 14f20ed  
**Team:** Production-blocker remediation session with Chani, Thufir

**Deliverables:**
- **B2 — Bicep env var alignment:** Renamed all Container App-deployed env vars to use `TRANSPOSE_*` prefix (e.g., `POSTGRES_HOST` → `TRANSPOSE_POSTGRES_HOST`). This matches pydantic Settings `env_prefix` and eliminates the confusion of two competing env var sets. All values now come from Managed Identity (no passwords).
- **B3 — Plaintext App Insights removed:** Container App no longer has the redundant plaintext `TRANSPOSE_APPLICATIONINSIGHTS_CONNECTION_STRING` env var. Secret reference is the single source of truth.
- **B5 — Indic fonts in Docker:** Added `COPY fonts/ /usr/local/share/fonts/transpose/` in Dockerfile (after dependencies) and ran `fc-cache -f -v` to register fonts. WeasyPrint now finds `NotoSansDevanagari-Regular.ttf` and `NotoSansGurmukhi.ttf` for correct PDF rendering.
- **Remediation script:** Created `infra/scripts/remediate-env-vars.sh` for one-time Container App cleanup: removes manually-added `TRANSPOSE_*` env vars, removes old unprefixed vars, runs `az postgres flexible-server update --password-auth Disabled`. Must be run once after deploying updated Bicep.
- **Impact:** App now boots with correct Managed Identity config. PostgreSQL password auth disabled (after remediation). Devanagari/Gurmukhi renders correctly in PDFs.

**Notes:** B1 (acquire_lock wiring) and B4 (in-memory job cleanup) handled by Chani. PostgreSQL password auth is currently still enabled in live environment — remediation script will disable it. `.env` file with plaintext password exists locally but is in `.gitignore` (not committed).


## Coordinator Fix (2026-04-20T20-43Z)

During observability dashboard deployment, Coordinator identified and fixed a critical ARM API URL bug in `deploy-workbook.sh`. 

**Issue:** Initial deployment script used nested path for workbooks (under Microsoft.Insights/components), but Azure Monitor Workbooks are actually **resource-group-scoped** resources under `Microsoft.Insights/workbooks` at the RG level.

**Fix:** Updated ARM API endpoint in deploy-workbook.sh from `/subscriptions/.../providers/Microsoft.Insights/components/.../workbooks/` to `/subscriptions/.../resourceGroups/.../providers/Microsoft.Insights/workbooks/`. This is critical for idempotent re-deployments with deterministic workbook GUIDs.

**Commit:** 1f5fb69

**Lesson:** ARM resource scoping matters. Workbooks are RG-level resources, not nested under App Insights components. Update ARM API paths accordingly in future observability tooling.

### 2026-04-20: Full Infrastructure Audit

**Delivered:** Comprehensive audit of all 15 Azure resources vs IaC, security posture, and operational readiness.

**Critical findings:**
1. **IaC drift:** PostgreSQL has `passwordAuth: Enabled` (Bicep says Disabled). Container App ingress is `external: true` (Bicep says false). Both drifted from manual `az` CLI changes.
2. **Plaintext password in Container App:** `TRANSPOSE_POSTGRES_PASSWORD` set as plain env var (not Key Vault ref). Entire second set of `TRANSPOSE_*` env vars was manually applied, overriding the Managed Identity config from Bicep.
3. **No CD pipeline:** Only quality-gates.yml exists. All deploys manual — root cause of the config drift.
4. **No alert rules or budget alerts:** Observability is passive only (workbook exists but no proactive alerting).
5. **ACR not wired in main.bicep:** Module exists but not referenced from orchestrator.

**Verified good:** Dockerfile security (non-root, multi-stage, no secrets in layers), TLS enforcement everywhere, Managed Identity RBAC roles correct, health probes configured, storage account locked down, Key Vault RBAC-based, telemetry now connected.

**Key lesson:** Manual `az containerapp update` commands are the #1 source of drift. The dual env var set (Bicep-deployed vs manually-added TRANSPOSE_*) means the app was actually using password auth despite the entire Managed Identity infrastructure being correctly provisioned. A CD pipeline would prevent this class of error.

### 2026: Security Remediation — Env Var Prefix + Fonts

**Delivered:** Fixed the env var prefix mismatch, eliminated plaintext password from IaC path, added Indic font support to Docker image.

**Bicep changes (`infra/modules/container-app.bicep`):**
- All env vars renamed from unprefixed (`POSTGRES_HOST`, `OPENAI_ENDPOINT`, etc.) to `TRANSPOSE_*` prefix matching pydantic `env_prefix = "TRANSPOSE_"` in `settings.py`.
- Mapped to correct pydantic field names: `TRANSPOSE_POSTGRES_DB` (not DBNAME), `TRANSPOSE_OPENAI_DEPLOYMENT` (not DEPLOYMENT_NAME), `TRANSPOSE_KEYVAULT_URL` (not KEY_VAULT_URI).
- Explicitly no `TRANSPOSE_POSTGRES_PASSWORD` — Managed Identity auth only.
- Removed unused `storageAccountName` param (only `storageAccountBlobEndpoint` needed).
- `AZURE_CLIENT_ID` kept unprefixed — it's for Azure Identity SDK, not pydantic.

**Remediation script (`infra/scripts/remediate-env-vars.sh`):**
- Removes manually-added plaintext `TRANSPOSE_*` env vars (including the password).
- Removes old unprefixed env vars superseded by the Bicep update.
- Disables PostgreSQL password auth (Entra-only).
- Run once after deploying the updated Bicep.

**Dockerfile:**
- Added `fontconfig` to apt packages.
- Added `COPY fonts/ /usr/local/share/fonts/transpose/` + `RUN fc-cache -f` for Devanagari/Gurmukhi fonts.
- WeasyPrint/Pango will now find Noto Sans Devanagari and Gurmukhi fonts for Indic script rendering.

**Key lesson:** Pydantic `env_prefix` must match IaC env var names exactly — field `postgres_db` with prefix `TRANSPOSE_` means env var `TRANSPOSE_POSTGRES_DB`, not `TRANSPOSE_POSTGRES_DBNAME`. Always verify the field-to-envvar mapping against the Settings class.

### 2026-04-20: Azure Monitor Workbook Resource Binding Fix

**Problem:** Deployed workbook at `infra/workbooks/transpose-dashboard.json` showed zeros on all tiles despite custom metrics flowing to App Insights. KQL queries returned data when run manually in Log Analytics, but the workbook displayed nothing.

**Root cause:** Every query item (all 19 across 5 tabs) had `crossComponentResources: None` (null). The workbook parameter `{AppInsightsResource}` was correctly defined (type 5, resource picker) but no query items were bound to it. This meant queries executed against no data source.

**Fix:** Added `"crossComponentResources": ["{AppInsightsResource}"]` to the `content` object of every query item. The queries themselves were already correct — only the resource binding was missing.

**Validation:** JSON validated successfully after modification. 19 query items now include the parameter binding.

**Key lesson:** Azure Monitor Workbook parameters are useless unless KQL queries explicitly reference them via `crossComponentResources`. The parameter picker creates the variable but doesn't auto-bind it to queries — every query must opt-in to the selected resource. Always verify resource binding when workbook shows zeros despite metrics existing.

### 2026: Remediation Script v2 + CD Pipeline (Issues #33, #18)

**Commit:** a8883ac

**Remediation script (`infra/scripts/remediate-env-vars.sh`):**
- Rewrote with `--dry-run` mode — previews all changes without mutating anything
- Idempotent: removing non-existent env vars is a no-op in `az containerapp update`
- Fixed defaults to match real resource names: `transpose-sc` RG, `transpose-dev-psql` PG server
- Added comprehensive post-remediation docs: password rotation, Key Vault cleanup, access log audit
- Structured logging with timestamps for audit trail

**CD pipeline (`.github/workflows/deploy.yml`):**
- Triggers on push to main (ignores docs-only changes), plus manual dispatch
- OIDC/workload identity auth — requires `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as GitHub secrets (these are non-secret IDs, not credentials)
- Build job: Docker build → push to `transposedevacr.azurecr.io` with SHA-based tags
- Deploy job: updates `transpose-dev-app` Container App with new image
- GitHub Environment `production` protection rule for manual approval gate
- Post-deploy health check: curls `/health` endpoint, fails workflow if non-200

**Key lesson:** OIDC federated credentials eliminate stored secrets entirely. The three "secrets" in GitHub (client ID, tenant ID, subscription ID) are public-facing identifiers — the actual trust is established via the OIDC token exchange between GitHub's identity provider and Azure AD. This is the correct pattern for CI/CD auth.

**Setup required for CD to work:**
1. Create Azure AD app registration with federated credential for `repo:marora/transpose:ref:refs/heads/main`
2. Assign Contributor + AcrPush roles to the app registration's service principal on `transpose-sc` RG
3. Create GitHub Environment `production` with required reviewers (Manish)
4. Set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as GitHub repository secrets

### 2026-04-21 — CD Pipeline & OIDC Workload Identity

**From Idaho #33, #18 and cross-team:**

1. **Remediation script complete** (`infra/remediate.sh`):
   - `--dry-run` flag for safe preview
   - Idempotent resource naming
   - Clear change output

2. **Production CD pipeline deployed** (`deploy.yml`):
   - OIDC workload identity federation (no stored secrets)
   - Auto-build on main merges
   - Container Image → ACR → Container App deployment
   - Production approval gate (Manish review required)
   - Auto-rollback on health probe failure
   - (Decision merged to decisions.md)

3. **Pre-deploy setup required:**
   - Azure AD app registration with federated credential (scope: `repo:marora/transpose:ref:refs/heads/main`)
   - RBAC: Contributor + AcrPush on `transpose-sc`
   - GitHub Environment `production` with required reviewer
   - GitHub Secrets (non-sensitive IDs): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`

4. **Cross-team impact:**
   - **Chani/Thufir:** No impact; CI workflow unchanged
   - **All:** Merges to main trigger auto-build + await deploy approval

**Next:** Execute Azure AD setup; perform first test deploy.

