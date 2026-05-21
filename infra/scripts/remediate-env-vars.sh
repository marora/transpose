#!/usr/bin/env bash
# remediate-env-vars.sh — Remediate Container App env var drift and PostgreSQL password auth
#
# The live Container App has manually-added plaintext env vars (including a PostgreSQL
# password) that conflict with Bicep-deployed Managed Identity config. This script:
#
#   1. Removes manually-added plaintext TRANSPOSE_* env vars (Bicep is source of truth)
#   2. Removes legacy unprefixed env vars from the original Bicep deployment
#   3. Disables PostgreSQL password authentication (Entra-only)
#   4. Documents password rotation procedure
#
# The script is idempotent — safe to run multiple times. Removing a non-existent env
# var is a no-op in `az containerapp update --remove-env-vars`.
#
# Prerequisites:
#   - az CLI authenticated (Contributor on resource group, or equivalent)
#   - Updated Bicep already deployed so TRANSPOSE_* vars come from IaC
#
# Usage:
#   ./infra/scripts/remediate-env-vars.sh                  # execute changes
#   ./infra/scripts/remediate-env-vars.sh --dry-run        # preview only, no mutations
#
# Environment overrides:
#   RESOURCE_GROUP=transpose-sc  CONTAINER_APP=transpose-dev-app  ./infra/scripts/remediate-env-vars.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — defaults match the transpose-sc resource group
# ---------------------------------------------------------------------------
RESOURCE_GROUP="${RESOURCE_GROUP:-transpose-sc}"
CONTAINER_APP="${CONTAINER_APP:-transpose-dev-app}"
PG_SERVER="${PG_SERVER:-transpose-dev-psql}"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[$(date -u +%H:%M:%SZ)] $*"; }
info() { log "INFO  $*"; }
warn() { log "WARN  $*"; }
run()  {
  if $DRY_RUN; then
    echo "  [DRY-RUN] $*"
  else
    "$@"
  fi
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
echo "=============================================="
echo "  Transpose — Environment Remediation Script"
echo "=============================================="
echo ""
info "Resource Group : $RESOURCE_GROUP"
info "Container App  : $CONTAINER_APP"
info "PostgreSQL     : $PG_SERVER"
if $DRY_RUN; then
  warn "DRY-RUN MODE — no changes will be made"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 1: Remove manually-added plaintext TRANSPOSE_* env vars
# ---------------------------------------------------------------------------
# These were added via `az containerapp update --set-env-vars` with plaintext
# values (including TRANSPOSE_POSTGRES_PASSWORD). The updated Bicep deploys
# these correctly with Managed Identity values, so the manual copies must go.
#
# Source of truth: infra/modules/container-app.bicep
# Correct env vars deployed by Bicep:
#   AZURE_CLIENT_ID              — MI client ID (for Azure Identity SDK)
#   TRANSPOSE_POSTGRES_HOST      — PostgreSQL FQDN
#   TRANSPOSE_POSTGRES_DB        — database name
#   TRANSPOSE_POSTGRES_USER      — MI client ID (token-based auth)
#   TRANSPOSE_OPENAI_ENDPOINT    — OpenAI endpoint URL
#   TRANSPOSE_OPENAI_DEPLOYMENT  — GPT-4o deployment name
#   TRANSPOSE_DOC_INTELLIGENCE_ENDPOINT — Document Intelligence endpoint
#   TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL  — Blob storage endpoint
#   TRANSPOSE_BLOB_STATIC_WEBSITE_URL   — Static Website endpoint
#   TRANSPOSE_KEYVAULT_URL       — Key Vault URI
#   TRANSPOSE_APPLICATIONINSIGHTS_CONNECTION_STRING — (secret ref)
#
# Notably absent from Bicep (by design):
#   TRANSPOSE_POSTGRES_PASSWORD  — MI auth, no password needed
# ---------------------------------------------------------------------------
info "Step 1/3: Removing manually-added plaintext env vars..."

MANUAL_VARS=(
  # Manually-added TRANSPOSE_* vars with plaintext values
  "TRANSPOSE_POSTGRES_HOST"
  "TRANSPOSE_POSTGRES_DBNAME"       # wrong field name (correct is TRANSPOSE_POSTGRES_DB)
  "TRANSPOSE_POSTGRES_USER"
  "TRANSPOSE_POSTGRES_PASSWORD"     # the exposed password — must be removed
  "TRANSPOSE_OPENAI_ENDPOINT"
  "TRANSPOSE_OPENAI_DEPLOYMENT"
  "TRANSPOSE_DOC_INTELLIGENCE_ENDPOINT"
  "TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL"
  "TRANSPOSE_BLOB_STATIC_WEBSITE_URL"
  "TRANSPOSE_KEYVAULT_URL"
  "TRANSPOSE_APPLICATIONINSIGHTS_CONNECTION_STRING"
)

for var in "${MANUAL_VARS[@]}"; do
  info "  Removing: $var"
done

run az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --remove-env-vars "${MANUAL_VARS[@]}" \
  --output none

info "  ✓ Plaintext env vars removed (Bicep-deployed values remain)"

# ---------------------------------------------------------------------------
# Step 2: Remove legacy unprefixed env vars (from original Bicep, pre-fix)
# ---------------------------------------------------------------------------
info "Step 2/3: Removing legacy unprefixed env vars..."

LEGACY_VARS=(
  "POSTGRES_HOST"
  "POSTGRES_DATABASE"
  "POSTGRES_USER"
  "DOCUMENT_INTELLIGENCE_ENDPOINT"
  "OPENAI_ENDPOINT"
  "OPENAI_DEPLOYMENT_NAME"
  "STORAGE_ACCOUNT_BLOB_ENDPOINT"
  "STORAGE_ACCOUNT_NAME"
  "KEY_VAULT_URI"
  "APPLICATIONINSIGHTS_CONNECTION_STRING"
)

for var in "${LEGACY_VARS[@]}"; do
  info "  Removing: $var"
done

run az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --remove-env-vars "${LEGACY_VARS[@]}" \
  --output none

info "  ✓ Legacy unprefixed env vars removed"

# ---------------------------------------------------------------------------
# Step 3: Disable PostgreSQL password authentication (Entra-only)
# ---------------------------------------------------------------------------
# Bicep declares passwordAuth: 'Disabled' but the live server drifted to
# passwordAuth: Enabled via manual CLI changes. This step re-enforces Entra-only.
# ---------------------------------------------------------------------------
info "Step 3/3: Disabling PostgreSQL password authentication..."

run az postgres flexible-server update \
  --name "$PG_SERVER" \
  --resource-group "$RESOURCE_GROUP" \
  --active-directory-auth Enabled \
  --password-auth Disabled \
  --output none

info "  ✓ PostgreSQL password auth disabled (Entra-only)"

# ---------------------------------------------------------------------------
# Summary and next steps
# ---------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  Remediation complete"
echo "=============================================="
if $DRY_RUN; then
  echo ""
  warn "This was a dry run. Re-run without --dry-run to apply changes."
fi
echo ""
echo "Post-remediation checklist:"
echo ""
echo "  1. VERIFY APP HEALTH"
echo "     curl https://\$(az containerapp show -n $CONTAINER_APP -g $RESOURCE_GROUP --query properties.configuration.ingress.fqdn -o tsv)/health"
echo ""
echo "  2. REDEPLOY BICEP (to ensure IaC state is canonical)"
echo "     az deployment group create -g $RESOURCE_GROUP -f infra/main.bicep -p infra/main.bicepparam"
echo ""
echo "  3. ROTATE THE EXPOSED POSTGRESQL PASSWORD"
echo "     The password that was set as a plaintext env var is now compromised."
echo "     Since password auth is now disabled, the password cannot be used."
echo "     However, to fully remediate:"
echo ""
echo "     a) If password auth was ever re-enabled, rotate it:"
echo "        az postgres flexible-server update \\"
echo "          --name $PG_SERVER --resource-group $RESOURCE_GROUP \\"
echo "          --admin-password \"\$(openssl rand -base64 32)\""
echo ""
echo "     b) Remove the password from any Key Vault secrets:"
echo "        az keyvault secret delete --vault-name transpose-dev-kv --name postgres-password"
echo ""
echo "     c) Purge local .env files that contain the old password"
echo "        (already in .gitignore — verify it was never committed)"
echo ""
echo "  4. AUDIT ACCESS LOGS"
echo "     Check PostgreSQL logs for any unauthorized access during the exposure window:"
echo "     az postgres flexible-server log list --name $PG_SERVER --resource-group $RESOURCE_GROUP"
echo ""
