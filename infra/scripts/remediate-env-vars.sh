#!/usr/bin/env bash
# remediate-env-vars.sh — One-time cleanup of manually-added env vars and password auth drift
#
# Run ONCE after deploying the updated Bicep templates (which now use TRANSPOSE_* prefix
# with Managed Identity values). This script removes the manually-added plaintext env vars
# and disables PostgreSQL password authentication.
#
# Prerequisites:
#   - az CLI authenticated with sufficient permissions
#   - Updated Bicep already deployed (so TRANSPOSE_* vars come from IaC)
#
# Usage:
#   chmod +x infra/scripts/remediate-env-vars.sh
#   ./infra/scripts/remediate-env-vars.sh

set -euo pipefail

# Configuration — update these to match your environment
RESOURCE_GROUP="${RESOURCE_GROUP:-transpose-dev-rg}"
CONTAINER_APP="${CONTAINER_APP:-transpose-dev-app}"
PG_SERVER="${PG_SERVER:-transpose-dev-pg}"

echo "=== Transpose Security Remediation ==="
echo "Resource Group:  $RESOURCE_GROUP"
echo "Container App:   $CONTAINER_APP"
echo "PostgreSQL:      $PG_SERVER"
echo ""

# -------------------------------------------------------
# Step 1: Remove manually-added plaintext env vars
# -------------------------------------------------------
echo "[1/3] Removing manually-added plaintext env vars from Container App..."

# These are the manually-added TRANSPOSE_* env vars that were set via 'az containerapp update'
# with plaintext values (including the password). The updated Bicep now deploys these correctly
# with Managed Identity values, so the manual ones must go.
VARS_TO_REMOVE=(
  "TRANSPOSE_POSTGRES_HOST"
  "TRANSPOSE_POSTGRES_DBNAME"
  "TRANSPOSE_POSTGRES_USER"
  "TRANSPOSE_POSTGRES_PASSWORD"
  "TRANSPOSE_OPENAI_ENDPOINT"
  "TRANSPOSE_DOC_INTELLIGENCE_ENDPOINT"
  "TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL"
  "TRANSPOSE_APPLICATIONINSIGHTS_CONNECTION_STRING"
)

REMOVE_ARGS=""
for var in "${VARS_TO_REMOVE[@]}"; do
  REMOVE_ARGS+="${var} "
done

az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --remove-env-vars $REMOVE_ARGS

echo "  ✓ Plaintext env vars removed"

# -------------------------------------------------------
# Step 2: Also remove old unprefixed env vars (from original Bicep)
# -------------------------------------------------------
echo "[2/3] Removing old unprefixed env vars (superseded by TRANSPOSE_* prefix)..."

OLD_VARS=(
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

OLD_REMOVE_ARGS=""
for var in "${OLD_VARS[@]}"; do
  OLD_REMOVE_ARGS+="${var} "
done

az containerapp update \
  --name "$CONTAINER_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --remove-env-vars $OLD_REMOVE_ARGS

echo "  ✓ Old unprefixed env vars removed"

# -------------------------------------------------------
# Step 3: Disable PostgreSQL password authentication
# -------------------------------------------------------
echo "[3/3] Disabling PostgreSQL password authentication (Entra-only)..."

az postgres flexible-server update \
  --name "$PG_SERVER" \
  --resource-group "$RESOURCE_GROUP" \
  --active-directory-auth Enabled \
  --password-auth Disabled

echo "  ✓ PostgreSQL password auth disabled (Entra-only)"

echo ""
echo "=== Remediation complete ==="
echo "Next steps:"
echo "  1. Re-deploy the Container App with updated Bicep: az deployment group create ..."
echo "  2. Verify the app starts and /health returns OK"
echo "  3. Rotate/revoke the old PostgreSQL password (transposeadmin)"
echo "  4. Delete the plaintext password from any Key Vault, config, or docs"
