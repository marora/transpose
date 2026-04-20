#!/usr/bin/env bash
# deploy-workbook.sh — Deploy the Transpose pipeline monitoring workbook to Azure Monitor.
#
# Usage:
#   ./deploy-workbook.sh -g <resource-group> [-s <subscription>] [-n <workbook-name>]
#
# Prerequisites:
#   - Azure CLI (az) authenticated
#   - An existing Application Insights resource in the target resource group

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKBOOK_FILE="${SCRIPT_DIR}/transpose-dashboard.json"

# Defaults
WORKBOOK_NAME="Transpose Pipeline Dashboard"
RESOURCE_GROUP=""
SUBSCRIPTION=""

usage() {
  echo "Usage: $0 -g <resource-group> [-s <subscription>] [-n <workbook-name>]"
  echo ""
  echo "  -g  Resource group containing the Application Insights resource (required)"
  echo "  -s  Azure subscription ID or name (optional, uses current default)"
  echo "  -n  Workbook display name (default: 'Transpose Pipeline Dashboard')"
  exit 1
}

while getopts "g:s:n:h" opt; do
  case $opt in
    g) RESOURCE_GROUP="$OPTARG" ;;
    s) SUBSCRIPTION="$OPTARG" ;;
    n) WORKBOOK_NAME="$OPTARG" ;;
    h) usage ;;
    *) usage ;;
  esac
done

if [[ -z "$RESOURCE_GROUP" ]]; then
  echo "Error: -g <resource-group> is required."
  usage
fi

if [[ ! -f "$WORKBOOK_FILE" ]]; then
  echo "Error: Workbook template not found at ${WORKBOOK_FILE}"
  exit 1
fi

# Resolve subscription flag
SUB_FLAG=""
if [[ -n "$SUBSCRIPTION" ]]; then
  SUB_FLAG="--subscription ${SUBSCRIPTION}"
fi

# Workbooks are resource-group-scoped resources; sourceId links to App Insights
# shellcheck disable=SC2086
RG_ID=$(az group show --name "$RESOURCE_GROUP" $SUB_FLAG --query id -o tsv)

echo "==> Looking up Application Insights resource in '${RESOURCE_GROUP}'..."
# shellcheck disable=SC2086
APP_INSIGHTS_ID=$(az monitor app-insights component show \
  --resource-group "$RESOURCE_GROUP" \
  $SUB_FLAG \
  --query "[0].id" -o tsv 2>/dev/null || true)

if [[ -z "$APP_INSIGHTS_ID" ]]; then
  echo "Warning: No Application Insights resource found. The workbook will be created"
  echo "         at the resource-group scope. You can link it to App Insights later."
  SOURCE_ID="$RG_ID"
else
  SOURCE_ID="$APP_INSIGHTS_ID"
  echo "    Found: ${APP_INSIGHTS_ID}"
fi

# Generate a deterministic GUID for the workbook (stable across re-deploys)
WORKBOOK_ID=$(python3 -c "
import uuid, sys
ns = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')
print(uuid.uuid5(ns, 'transpose-pipeline-dashboard-${RESOURCE_GROUP}'))
" 2>/dev/null || uuidgen)

echo "==> Deploying workbook '${WORKBOOK_NAME}' (ID: ${WORKBOOK_ID})..."

# Read the workbook template as serialized JSON string for the ARM API
SERIALIZED_CONTENT=$(python3 -c "
import json, sys
with open('${WORKBOOK_FILE}') as f:
    data = json.load(f)
print(json.dumps(json.dumps(data)))
" 2>/dev/null)

if [[ -z "$SERIALIZED_CONTENT" ]]; then
  echo "Error: Failed to serialize workbook JSON."
  exit 1
fi

# Deploy using az rest (direct ARM API call for maximum compatibility)
# shellcheck disable=SC2086
LOCATION=$(az group show --name "${RESOURCE_GROUP}" $SUB_FLAG --query location -o tsv)

az rest --method PUT \
  --url "https://management.azure.com${RG_ID}/providers/Microsoft.Insights/workbooks/${WORKBOOK_ID}?api-version=2022-04-01" \
  --body "{
    \"location\": \"${LOCATION}\",
    \"kind\": \"shared\",
    \"properties\": {
      \"displayName\": \"${WORKBOOK_NAME}\",
      \"serializedData\": ${SERIALIZED_CONTENT},
      \"category\": \"workbook\",
      \"sourceId\": \"${SOURCE_ID}\"
    },
    \"tags\": {
      \"project\": \"transpose\",
      \"hidden-title\": \"${WORKBOOK_NAME}\"
    }
  }" \
  --output table

echo ""
echo "==> Workbook deployed successfully!"
echo ""
echo "To view the workbook:"
echo "  1. Go to Azure Portal → Resource Group '${RESOURCE_GROUP}'"
echo "  2. Find '${WORKBOOK_NAME}' in resources (type: Azure Workbook)"
echo "  3. Or: Monitor → Workbooks → '${WORKBOOK_NAME}'"
echo ""
echo "To view in Application Insights:"
echo "  1. Go to your App Insights resource"
echo "  2. Left menu → Investigate → Workbooks"
echo "  3. Find '${WORKBOOK_NAME}' under 'Recently modified' or 'All'"
