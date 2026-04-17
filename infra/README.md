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
| **Azure Container Apps** | Compute runtime | 1 core, 2Gi, 0-3 replicas | User-Assigned MI |
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
├── modules/
│   ├── monitoring.bicep          # Application Insights + Log Analytics
│   ├── storage.bicep             # Blob Storage (source-pdfs, output)
│   ├── keyvault.bicep            # Key Vault (for future secrets)
│   ├── database.bicep            # PostgreSQL Flexible Server (Entra auth, auto-pause)
│   ├── cognitive-services.bicep  # Document Intelligence + OpenAI + GPT-4o deployment
│   ├── identity.bicep            # User-Assigned Managed Identity + RBAC roles
│   └── container-app.bicep       # Container Apps Environment + Container App
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
| Container Apps | 1 core, 2Gi, 0-3 replicas | ~$10-30 (usage-based) |
| Azure OpenAI | GPT-4o, 30K TPM | Usage-based (see below) |
| Document Intelligence | S0 | Usage-based (see below) |
| Key Vault | Standard | ~$0.03/10K ops |

**Usage-based costs:**
- **Azure OpenAI (GPT-4o)**: ~$2.50 per 1M input tokens, ~$10 per 1M output tokens
  - Estimated for a 300-page book: ~$15-30
- **Document Intelligence (prebuilt-read)**: $1.50 per 1000 pages
  - Estimated for a 300-page book: ~$0.45

**Total estimated dev environment cost**: ~$20-70/month + per-book processing costs

**Serverless savings:** Redis removed (~$16/mo savings). PostgreSQL auto-pause reduces idle cost to near-zero.

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

All resources are instrumented with Application Insights and Log Analytics.

**Key queries:**

```kusto
// Pipeline stage duration
customMetrics
| where name == "transpose.pipeline.stage_duration"
| summarize avg(value), max(value), min(value) by tostring(customDimensions.stage)

// OpenAI token usage
customMetrics
| where name == "transpose.openai.tokens_used"
| summarize sum(value) by bin(timestamp, 1h)

// Error rate by stage
exceptions
| summarize count() by tostring(customDimensions.stage), bin(timestamp, 1h)
```

**Dashboards:** Import the Application Insights workbook from `.squad/observability/` (if available).

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
az group delete --name transpose-dev --yes --no-wait
```

**Warning:** This is irreversible. All data will be lost.

## Support

For issues or questions:
- File an issue in the GitHub repository
- Contact the Transpose team via the `.squad/` coordination files
- Check the architecture documentation: `docs/architecture.md`

---

**Infrastructure Owner:** Idaho (Cloud/Infrastructure Developer)  
**Last Updated:** 2024  
**Version:** 1.0.0
