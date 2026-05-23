# Transpose Infrastructure

This directory contains the Azure infrastructure as code (Bicep) for the Transpose literary translation pipeline.

## Architecture Overview

The infrastructure provisions the following Azure services:

| Service | Purpose | SKU (Phase 1) | Auth |
|---------|---------|---------------|------|
| **Azure AI Document Intelligence** | OCR for scanned PDFs | S0 | Managed Identity |
| **Azure OpenAI** | Literary translation (GPT-4o) | S0, 30K TPM | Managed Identity |
| **Azure Blob Storage** | Source PDFs + output files | Standard_LRS | Managed Identity |
| **Azure Key Vault** | Future secret storage | Standard | RBAC (Managed Identity) |
| **Azure Container Apps** | Compute runtime (main app + LaBSE sidecar) | 2 vCPU, 6Gi per replica (main: 1 vCPU/2Gi, LaBSE: 1 vCPU/4Gi) | User-Assigned MI |
| **Application Insights** | Traces, metrics, logs | — | Connection string |
| **PostgreSQL Flexible Server** | Persistent state + pipeline tracking | Burstable B1ms | Entra auth only |
| **Log Analytics Workspace** | Backend for App Insights | PerGB2018 | — |

**Security:** All services use Managed Identity for authentication. No secrets in code or configuration files.

**Serverless Architecture:** Redis removed — pipeline state tracked in PostgreSQL. PostgreSQL auto-pause enabled for near-zero idle costs.

## Directory Structure

```
infra/
├── main.bicep              # Entry point — orchestrates all modules
├── main.bicepparam         # Parameter file with defaults
├── main.json               # Compiled ARM template
├── modules/
│   ├── monitoring.bicep          # Application Insights + Log Analytics
│   ├── storage.bicep             # Blob Storage (source-pdfs, output)
│   ├── keyvault.bicep            # Key Vault (for future secrets)
│   ├── database.bicep            # PostgreSQL Flexible Server (Entra auth, auto-pause)
│   ├── cognitive-services.bicep  # Document Intelligence + OpenAI + GPT-4o deployment
│   ├── identity.bicep            # User-Assigned Managed Identity + RBAC roles
│   ├── container-app.bicep       # Container Apps Environment + Container App (main + LaBSE sidecar)
│   ├── sre-agent.bicep           # Azure SRE Agent + dedicated UAMI (gated by deployAgent param)
│   └── acr.bicep                 # Azure Container Registry module
├── labse/
│   ├── Dockerfile                # LaBSE embedding sidecar image (weights baked in)
│   ├── app.py                    # Flask service for embeddings (POST /embed, GET /health)
│   └── docker-compose.yml        # Local dev stub for Trinity's Layer A work
├── scripts/
│   └── init-db.sql         # PostgreSQL schema initialization (includes pipeline_state)
└── README.md               # This file
```

## Prerequisites

1. **Azure CLI** (v2.50.0 or later)
   ```bash
   az --version
   ```

2. **Bicep CLI** (v0.20.0 or later)
   ```bash
   az bicep version
   ```

3. **Azure Subscription** with the following providers registered:
   - Microsoft.App
   - Microsoft.CognitiveServices
   - Microsoft.DBforPostgreSQL
   - Microsoft.Storage
   - Microsoft.KeyVault
   - Microsoft.ManagedIdentity
   - Microsoft.Insights

4. **Permissions**: You need `Owner` or `Contributor` + `User Access Administrator` roles on the subscription or resource group.

5. **Resource Group**: Create a resource group for the deployment
   ```bash
   az group create --name transpose-dev --location eastus
   ```

## Deployment

### Step 1: Validate the Bicep template

```bash
cd /path/to/transpose
az bicep build --file infra/main.bicep
```

### Step 2: Deploy infrastructure

**Option A: Using the parameter file (recommended)**

```bash
az deployment group create \
  --resource-group transpose-dev \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

**Option B: Override parameters inline**

```bash
az deployment group create \
  --resource-group transpose-dev \
  --template-file infra/main.bicep \
  --parameters environmentName=staging \
  --parameters allowPublicPostgresAccess=false
```

**Option C: What-If deployment (dry run)**

```bash
az deployment group what-if \
  --resource-group transpose-dev \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam
```

Deployment takes approximately **15-20 minutes**.

### Step 3: Capture deployment outputs

```bash
az deployment group show \
  --resource-group transpose-dev \
  --name main \
  --query properties.outputs
```

Save these values — you'll need them for environment configuration and database initialization.

### Step 4: Initialize the PostgreSQL database

After the infrastructure is deployed, run the schema migration:

```bash
# Get the PostgreSQL server name
POSTGRES_SERVER=$(az deployment group show \
  --resource-group transpose-dev \
  --name main \
  --query properties.outputs.postgresServerName.value -o tsv)

# Get your Azure AD access token
az login

# Connect to the database as the managed identity admin
# (You may need to add your IP to the firewall temporarily)
az postgres flexible-server firewall-rule create \
  --resource-group transpose-dev \
  --name $POSTGRES_SERVER \
  --rule-name AllowMyIP \
  --start-ip-address $(curl -s ifconfig.me) \
  --end-ip-address $(curl -s ifconfig.me)

# Run the initialization script
psql "host=${POSTGRES_SERVER}.postgres.database.azure.com port=5432 dbname=transpose user=$(az account show --query user.name -o tsv) sslmode=require" \
  -f infra/scripts/init-db.sql
```

Alternatively, connect using Azure Data Studio or pgAdmin with Entra authentication.

### Step 4.5: Enable PostgreSQL auto-pause (optional — for cost savings)

To enable automatic server pause when idle (reduces costs to near-zero):

```bash
# Get the PostgreSQL server name
POSTGRES_SERVER=$(az deployment group show \
  --resource-group transpose-dev \
  --name main \
  --query properties.outputs.postgresServerName.value -o tsv)

# Enable auto-pause (note: some regions/SKUs may not support this feature yet)
az postgres flexible-server update \
  --resource-group transpose-dev \
  --name $POSTGRES_SERVER \
  --auto-grow Disabled

# Verify configuration
az postgres flexible-server show \
  --resource-group transpose-dev \
  --name $POSTGRES_SERVER \
  --query '{name:name, tier:sku.tier, autoGrow:storage.autoGrow}'
```

**Note:** Auto-pause/auto-stop for PostgreSQL Flexible Server may not be available in all regions or API versions. Check Azure documentation for current availability.

### Step 5: Build and push the container image

```bash
# Build the Docker image
docker build -t transpose:latest .

# Tag and push to Azure Container Registry (if using ACR)
# az acr login --name <your-acr-name>
# docker tag transpose:latest <your-acr-name>.azurecr.io/transpose:latest
# docker push <your-acr-name>.azurecr.io/transpose:latest

# Update the Container App with the new image
az containerapp update \
  --resource-group transpose-dev \
  --name transpose-dev-app \
  --image <your-acr-name>.azurecr.io/transpose:latest
```

## Environment Variables

The Container App is pre-configured with these environment variables:

| Variable | Source | Description |
|----------|--------|-------------|
| `AZURE_CLIENT_ID` | Managed Identity | Client ID for Azure authentication |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Key Vault secret | Application Insights connection string |
| `DOCUMENT_INTELLIGENCE_ENDPOINT` | Output | Document Intelligence API endpoint |
| `OPENAI_ENDPOINT` | Output | Azure OpenAI API endpoint |
| `OPENAI_DEPLOYMENT_NAME` | Output | GPT-4o deployment name |
| `STORAGE_ACCOUNT_BLOB_ENDPOINT` | Output | Blob Storage endpoint |
| `STORAGE_ACCOUNT_NAME` | Output | Storage account name |
| `POSTGRES_HOST` | Output | PostgreSQL server FQDN |
| `POSTGRES_DATABASE` | Output | Database name (transpose) |
| `POSTGRES_USER` | Managed Identity | Client ID for Entra auth |
| `KEY_VAULT_URI` | Output | Key Vault URI |

The application code should use `DefaultAzureCredential` from the Azure SDK to authenticate.

## Local Development

For local development, use Docker Compose:

```bash
# Start local services (PostgreSQL only — Redis removed)
docker-compose up -d

# Initialize the local database
docker-compose exec postgres psql -U transpose -d transpose -f /docker-entrypoint-initdb.d/init.sql

# Run the application locally
# (Configure Azure service endpoints via environment variables or .env file)
```

See `docker-compose.yml` for service configuration. Pipeline state is tracked in PostgreSQL `pipeline_state` table.

## Cost Estimation (Dev Environment)

Approximate monthly costs for the Phase 1 dev environment (US East region):

| Service | SKU | Monthly Cost (USD) |
|---------|-----|-------------------|
| PostgreSQL Flexible Server | B1ms (with auto-pause) | ~$0-12 (near-zero when idle) |
| Storage Account | Standard_LRS | ~$1-5 (usage-based) |
| Log Analytics + App Insights | PerGB2018 | ~$5-20 (usage-based) |
| Container Apps | 1 core, 2Gi, 0-5 replicas | ~$0 when idle; usage-based when active |
| Azure OpenAI | GPT-4o, 30K TPM | Usage-based (see below) |
| Document Intelligence | S0 | Usage-based (see below) |
| Key Vault | Standard | ~$0.03/10K ops |

**Usage-based costs:**
- **Azure OpenAI (GPT-4o)**: ~$2.50 per 1M input tokens, ~$10 per 1M output tokens
  - Estimated for a 300-page book: ~$15-30
- **Document Intelligence (prebuilt-read)**: $1.50 per 1000 pages
  - Estimated for a 300-page book: ~$0.45

**Total estimated dev environment cost**: ~$20-70/month + per-book processing costs

**Serverless savings:** Redis removed (~$16/mo savings). PostgreSQL auto-pause reduces idle cost to near-zero. Container Apps default to `minReplicas=0` so dev scales to zero after the idle window; Application Insights telemetry remains app-level instrumentation and resumes on cold start.

**Cost guardrail:** The dev Bicep parameters provision a $25/month resource-group budget alert with notifications at 50%, 80%, and 100%. This intentionally catches dormant-cost regressions early after the prior dormant environment burned hundreds of dollars.

```bash
# Recreate or update the RG budget alert with the current deployed image preserved
CURRENT_IMAGE=$(az containerapp show --resource-group transpose-sc --name transpose-dev-app --query properties.template.containers[0].image -o tsv)
REGISTRY_SERVER=$(az containerapp show --resource-group transpose-sc --name transpose-dev-app --query properties.configuration.registries[0].server -o tsv)
az deployment group create \
  --resource-group transpose-sc \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters containerImage="$CURRENT_IMAGE" containerRegistryServer="$REGISTRY_SERVER"

az consumption budget list --resource-group transpose-sc -o table
```

### Azure SRE Agent lifecycle (cost-aware up/down)

The Azure SRE Agent (`Microsoft.App/agents`) is the largest single contributor to dormant cost (~$10/day idle, ~$300/month). It is now declared in `modules/sre-agent.bicep` and gated by the `deployAgent` parameter so it can be torn down between active translation runs without losing the rest of the IaC.

**Provision (default):** `deployAgent=true` in `main.bicepparam`. The standard `az deployment group create` flow creates (or adopts, idempotently) the agent and its dedicated UAMI. Re-up from a torn-down state takes <5 minutes; the knowledge graph then rebuilds in the background (`runningState: BuildingKnowledgeGraph`) while the agent is otherwise usable.

**Tear down:** Bicep incremental deployments do **not** delete resources by omission. Use the explicit `az resource delete` form:

```bash
RG=transpose-sc
AGENT_NAME=transpose-sc-agent
AGENT_UAMI=transpose-sc-agent-5h56rfksrqb24

# 1) Delete the agent (stops billing immediately)
az resource delete -g "$RG" -n "$AGENT_NAME" \
  --resource-type Microsoft.App/agents --api-version 2025-05-01-preview

# 2) Delete the dedicated UAMI (UAMIs are free but tidy up)
az identity delete -g "$RG" -n "$AGENT_UAMI"

# 3) Flip the bicep parameter so future deployments don't recreate it
sed -i 's/^param deployAgent = true$/param deployAgent = false/' infra/main.bicepparam
```

**Re-up after teardown:** set `deployAgent = true` in `main.bicepparam` and redeploy. If you tore down without preserving the original randomly-suffixed UAMI name (`transpose-sc-agent-5h56rfksrqb24`), also clear `agentName` and `agentIdentityName` so the bicep falls back to the deterministic `${namePrefix}-agent` / `${namePrefix}-agent-identity` defaults.

**Future work (issue #102 policy layer):** dormancy-signal-driven auto-teardown via GitHub Action, activity-protection check against `book_validation_reports`. Blocked until this IaC adoption ships; tracked in [#102](https://github.com/marora/transpose/issues/102).

### Manual idle / scale-to-zero checks

```bash
# Force the dev app floor to zero if emergency manual remediation is needed
az containerapp update \
  --resource-group transpose-sc \
  --name transpose-dev-app \
  --min-replicas 0

# Verify the configured floor and active revision
az containerapp show \
  --resource-group transpose-sc \
  --name transpose-dev-app \
  --query '{minReplicas:properties.template.scale.minReplicas, revision:properties.latestRevisionName}'

# After 10-15 minutes idle, this should return []
az containerapp replica list \
  --resource-group transpose-sc \
  --name transpose-dev-app \
  --revision $(az containerapp revision list --resource-group transpose-sc --name transpose-dev-app --query "[?properties.active].name | [0]" -o tsv)
```

**Production recommendations:**
- Scale PostgreSQL to General Purpose
- Enable geo-redundancy for Storage
- Disable public network access on all services
- Add VNet integration and Private Endpoints

## Networking (Production Hardening)

For production deployments:

1. **Disable public access:**
   - Set `allowPublicPostgresAccess=false`
   - Configure private endpoints for all services
   - Use VNet integration for Container Apps

2. **Add firewall rules:**
   - Restrict storage account to Azure services only
   - Configure NSGs on subnets
   - Enable Azure Firewall or Application Gateway

3. **Enable advanced security:**
   - Microsoft Defender for Cloud
   - Azure DDoS Protection
   - Key Vault with purge protection and soft delete

## Monitoring and Observability

All resources are instrumented with Application Insights and Log Analytics via OpenTelemetry (`azure-monitor-opentelemetry`).

**Full documentation:** See [`docs/observability.md`](../docs/observability.md) for:
- Azure Portal navigation (2026 UI)
- KQL queries for all custom metrics
- Alert setup and thresholds
- Troubleshooting runbooks

### Quick Start: Import the Dashboard Workbook

```bash
# Deploy the pre-built Azure Monitor Workbook
cd infra/workbooks
./deploy-workbook.sh -g transpose-dev
```

Or import manually: Azure Portal → App Insights → **Monitoring** → **Workbooks** → New → Advanced Editor → paste contents of `infra/workbooks/transpose-dashboard.json`.

The workbook provides five tabs: Pipeline Overview, Translation Performance, OCR & Quality, Infrastructure Health, and Errors & Alerts.

### Quick KQL Check

```kusto
// Pipeline health summary (run in App Insights → Monitoring → Logs)
customMetrics
| where name startswith "transpose."
| summarize total = sum(value), latest = max(timestamp) by name
| order by latest desc
```

## Troubleshooting

### Common Issues

**1. "Cognitive Services OpenAI User" role assignment fails**
- Ensure the managed identity is created before role assignment
- Wait 60 seconds after identity creation for propagation
- Re-run the deployment

**2. PostgreSQL connection fails**
- Verify firewall rules allow your IP
- Confirm Entra authentication is enabled
- Check that managed identity is set as admin

**3. Container App can't pull image**
- Verify ACR credentials or managed identity has `AcrPull` role
- Check container registry server in parameters

**4. Key Vault access denied**
- Confirm managed identity has "Key Vault Secrets User" role
- Check RBAC authorization is enabled (not access policies)

### Diagnostic Commands

```bash
# Check deployment status
az deployment group show --resource-group transpose-dev --name main

# Test PostgreSQL connectivity
az postgres flexible-server connect \
  --name transpose-dev-psql \
  --admin-user <your-email> \
  --database transpose

# Check Container App logs
az containerapp logs show \
  --resource-group transpose-dev \
  --name transpose-dev-app \
  --follow

# List managed identity role assignments
az role assignment list \
  --assignee $(az identity show --resource-group transpose-dev --name transpose-dev-identity --query principalId -o tsv) \
  --all
```

## Clean Up

To delete all resources:

```bash
az group delete --name transpose-sc --yes --no-wait
```

**Warning:** This is irreversible. All data will be lost.

## Support

For issues or questions:
- File an issue in the GitHub repository
- Contact the Transpose team via the `.squad/` coordination files
- Check the architecture documentation: `docs/architecture.md`

---

**Infrastructure Owner:** Idaho (Cloud/Infrastructure Developer)  
**Last Updated:** 2026  
**Version:** 1.0.0

---

## LaBSE Sidecar (Oracle Translation Quality Score Layer A)

The Container App includes a **LaBSE sidecar container** for multilingual embedding similarity scoring (Oracle Layer A).

### Configuration

- **Image:** Built from `infra/labse/Dockerfile` (weights baked in at build time)
- **Resources:** 1 vCPU, 4 GiB memory
- **Endpoint:** `http://localhost:8500` (internal loopback — main container accesses via localhost)
- **Model:** `sentence-transformers/LaBSE` (109 languages, 768-dim embeddings, ~1.8 GB)
- **API:**
  - `POST /embed` — Generate embeddings for text list
  - `GET /health` — Readiness check (returns 200 once model loaded)

### Building and Deploying the Sidecar

```bash
# 1. Build the LaBSE image (from repo root)
az acr build \
  --registry <your-acr-name> \
  --image labse:latest \
  --file infra/labse/Dockerfile \
  .

# 2. Deploy infrastructure with LaBSE image
az deployment group create \
  --resource-group transpose-dev \
  --template-file infra/main.bicep \
  --parameters infra/main.bicepparam \
  --parameters labseImage="<your-acr-name>.azurecr.io/labse:latest" \
  --parameters containerRegistryServer="<your-acr-name>.azurecr.io"
```

**Note:** If `labseImage` parameter is empty, the sidecar deploys with a placeholder image. The main app container will still boot but Layer A scoring will be unavailable.

### Local Development (Trinity)

Run the LaBSE sidecar locally for Layer A development:

```bash
# From repo root
docker compose -f infra/labse/docker-compose.yml up

# Test the endpoint
curl -X POST http://localhost:8765/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["शांति", "peace"]}'

# Returns:
# {
#   "embeddings": [[0.123, -0.456, ...], [0.789, -0.234, ...]],
#   "count": 2,
#   "dimensions": 768
# }
```

The local service listens on **port 8765** (matches the Container App internal :8500 convention).

### Failure Modes

Per Oracle spec (`.squad/decisions-archive.md`), Layer A failures degrade gracefully:

| Failure | Detection | Pipeline Behavior |
|---------|-----------|-------------------|
| **Sidecar OOM** | Container restart event, HTTP 502 from :8500 | Skip Layer A for the book; mark `quality.layer_a.available = false` |
| **Sidecar not ready** | `/health` returns non-200 | Same as OOM; should be rare with `minReplicas=1` |

Trinity's quality scoring client should always check `/health` before calling `/embed`, and surface Layer A unavailability to the dashboard (Tier 1 + Layer C composite only).

### Cost Impact

- **Idle cost:** ~$60/month (sidecar memory + CPU reservation with `minReplicas=1`)
- **Per-book cost:** ~$0 (self-hosted, ~6s CPU per 300-page book)
- **Total Container App per replica:** 2 vCPU / 6 GiB (main: 1 vCPU/2Gi, LaBSE: 1 vCPU/4Gi)
- **SKU:** No upgrade required — Container Apps Consumption supports up to 4 vCPU / 8 GiB per replica

### Endpoint Convention for Trinity

**Main app accesses LaBSE sidecar via:** `TRANSPOSE_LABSE_ENDPOINT=http://localhost:8500`

This environment variable is pre-configured in the Container App bicep (`infra/modules/container-app.bicep`). Trinity's `src/transpose/config/settings.py` should define:

```python
labse_endpoint: str = "http://localhost:8500"
```

Local dev overrides via `.env`:

```bash
TRANSPOSE_LABSE_ENDPOINT=http://localhost:8765
```

---

## Key Vault Secret: `anthropic-api-key`

For Oracle Layer C (Claude Sonnet 4.5 judge), the Anthropic API key is stored in Key Vault as:

**Secret name:** `anthropic-api-key`

Trinity's #104 (Anthropic Sonnet judge) should reference this secret name when implementing the Layer C client. The Container App will expose it via `TRANSPOSE_ANTHROPIC_API_KEY` environment variable (to be wired in a follow-up infra PR).

**Local dev:** Add to `.env`:

```bash
TRANSPOSE_ANTHROPIC_API_KEY=sk-ant-...
```

**Security:** Never log or commit this key. Use `pydantic.SecretStr` for automatic repr-masking.

