#!/usr/bin/env bash
# =============================================================================
# azure-setup.sh — Transpose Azure Storage + Static Website Setup
# =============================================================================
# Provisions all Azure resources required for Shape A (private workbench +
# WhatsApp-preview landing pages).  Idempotent: safe to re-run if a step was
# previously completed.
#
# PREREQUISITES
#   • az login already done in a separate terminal (Manish handles this)
#   • Azure CLI ≥ 2.60 installed
#
# USAGE
#   chmod +x scripts/azure-setup.sh
#   ./scripts/azure-setup.sh                   # run for real
#   ./scripts/azure-setup.sh --dry-run         # print commands, execute nothing
#
# DATE: 2026-05-20T23:19:30-04:00
# =============================================================================

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# VARIABLES — override any of these before running to customise your deployment
# ─────────────────────────────────────────────────────────────────────────────
RESOURCE_GROUP="${RESOURCE_GROUP:-transpose-rg}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-transposebooks}"
LOCATION="${LOCATION:-eastus}"

# Private container: book source PDFs, translated PDFs, workspace artifacts
CONTAINER_BOOK_WORKSPACES="${CONTAINER_BOOK_WORKSPACES:-book-workspaces}"

# Static Website documents (served from $web container, auto-created by Azure)
STATIC_INDEX_DOC="index.html"
STATIC_ERROR_DOC="404.html"

# Path to robots.txt relative to this script (used for upload in Step 8)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROBOTS_TXT="${SCRIPT_DIR}/robots.txt"

# ─────────────────────────────────────────────────────────────────────────────
# DRY-RUN SUPPORT
# ─────────────────────────────────────────────────────────────────────────────
DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  DRY-RUN MODE — commands printed, nothing executed           ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
fi

# Helper: run a command or, in dry-run mode, just print it.
run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  [DRY-RUN] $*"
    else
        "$@"
    fi
}

is_rbac_propagation_error() {
    local output_lower="${1,,}"

    [[ "$output_lower" == *"do not have the required permissions"* ]] ||
        [[ "$output_lower" == *"storage blob data contributor"* ]] ||
        [[ "$output_lower" == *"authorizationpermissionmismatch"* ]] ||
        [[ "$output_lower" == *"this request is not authorized"* ]] ||
        [[ "$output_lower" == *"insufficientaccountpermissions"* ]] ||
        [[ "$output_lower" == *"status code: 403"* ]]
}

retry_on_rbac_lag() {
    local success_message="$1"
    shift

    local max_attempts=6
    local delays=(15 30 60 60 60)
    local attempt=1
    local start_seconds=$SECONDS
    local output=""
    local status=0
    local elapsed=0
    local sleep_seconds=0

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "  [DRY-RUN] $*"
        return 0
    fi

    while (( attempt <= max_attempts )); do
        set +e
        output="$("$@" 2>&1)"
        status=$?
        set -e

        if (( status == 0 )); then
            [[ -n "$output" ]] && echo "$output"
            if (( attempt > 1 )); then
                elapsed=$((SECONDS - start_seconds))
                echo "✅ ${success_message} (${elapsed} seconds total)"
            fi
            return 0
        fi

        if ! is_rbac_propagation_error "$output"; then
            echo "$output" >&2
            return "$status"
        fi

        echo "$output" >&2

        if (( attempt == max_attempts )); then
            elapsed=$((SECONDS - start_seconds))
            echo "❌ Storage RBAC did not finish propagating after ${elapsed} seconds (${max_attempts} attempts)." >&2
            echo "   Re-run this script in a couple of minutes, or use --auth-mode key as an escape hatch if you must bypass data-plane login temporarily." >&2
            return "$status"
        fi

        sleep_seconds="${delays[$((attempt - 1))]}"
        echo "⏳ Waiting for RBAC role propagation… (attempt $((attempt + 1))/${max_attempts}, sleeping ${sleep_seconds}s)" >&2
        sleep "$sleep_seconds"
        attempt=$((attempt + 1))
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 0: Confirm active Azure subscription
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 0: Confirm active Azure subscription"
echo "══════════════════════════════════════════════════════════════════════"
# This is a read-only check — always run even in dry-run mode so you can
# see which subscription will be targeted.
echo ""
echo "Active subscription:"
az account show --query "{name:name, subscriptionId:id, state:state}" -o table
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Create resource group (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 1: Create resource group → ${RESOURCE_GROUP} (${LOCATION})"
echo "══════════════════════════════════════════════════════════════════════"
# --output table is purely cosmetic; re-running this on an existing group
# returns a "properties.provisioningState: Succeeded" row — that is correct.
echo ""
run az group create \
    --name "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --output table
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Create storage account (idempotent)
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 2: Create storage account → ${STORAGE_ACCOUNT}"
echo "══════════════════════════════════════════════════════════════════════"
# Storage account names must be globally unique, 3–24 chars, lowercase
# alphanumeric only.  If 'transposebooks' is taken, set STORAGE_ACCOUNT to
# something like 'transposebksmr' (append your initials).
#
# --allow-blob-public-access false: no container may be made public.
#   The Static Website $web container is an exception managed by Azure itself
#   and is unaffected by this flag — it will still serve HTML publicly.
# --min-tls-version TLS1_2: enforces modern TLS for all data-plane operations.
echo ""
run az storage account create \
    --name "${STORAGE_ACCOUNT}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --allow-blob-public-access false \
    --min-tls-version TLS1_2 \
    --output table
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Create private container — book-workspaces
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 3: Create private container → ${CONTAINER_BOOK_WORKSPACES}"
echo "══════════════════════════════════════════════════════════════════════"
# --public-access off: no anonymous reads.  All access is via SAS tokens
# generated by Manish (or the pipeline) on demand.
# --auth-mode login: uses Manish's Entra ID identity (not a storage key).
#   This requires the Storage Blob Data Contributor role assigned in Step 5.
echo ""
run az storage container create \
    --name "${CONTAINER_BOOK_WORKSPACES}" \
    --account-name "${STORAGE_ACCOUNT}" \
    --auth-mode login \
    --public-access off \
    --output table
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Enable Static Website feature
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 4: Enable Static Website (creates \$web container)"
echo "══════════════════════════════════════════════════════════════════════"
# Enabling the static website feature on the storage account automatically
# creates the $web container (public, read-only, no directory listing).
# The $web container is where per-book landing pages (index.html) are uploaded.
# URL pattern: https://<account>.z<n>.web.core.windows.net/<slug>--<book_id>/
#
# Note: --404-document is optional; 404.html lets us return a branded page
# for unknown book slugs instead of Azure's raw XML 404.
echo ""
run az storage blob service-properties update \
    --account-name "${STORAGE_ACCOUNT}" \
    --static-website \
    --index-document "${STATIC_INDEX_DOC}" \
    --404-document "${STATIC_ERROR_DOC}" \
    --auth-mode login
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Assign Storage Blob Data Contributor to current user
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 5: Assign Storage Blob Data Contributor to signed-in user"
echo "══════════════════════════════════════════════════════════════════════"
# This role grants Manish full read/write access to blobs via --auth-mode login.
# Required for: container create, blob upload, SAS token generation (--as-user),
# and any pipeline operation that writes to book-workspaces.
#
# The role assignment is at the storage account scope, covering all containers.
echo ""
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY-RUN] ACCOUNT_ID=\$(az storage account show --name ${STORAGE_ACCOUNT} --resource-group ${RESOURCE_GROUP} --query id -o tsv)"
    echo "  [DRY-RUN] USER_ID=\$(az ad signed-in-user show --query id -o tsv)"
    echo "  [DRY-RUN] az role assignment create \\"
    echo "              --role \"Storage Blob Data Contributor\" \\"
    echo "              --assignee \"\$USER_ID\" \\"
    echo "              --scope \"\$ACCOUNT_ID\" \\"
    echo "              --output table"
else
    ACCOUNT_ID=$(az storage account show \
        --name "${STORAGE_ACCOUNT}" \
        --resource-group "${RESOURCE_GROUP}" \
        --query id -o tsv)

    USER_ID=$(az ad signed-in-user show --query id -o tsv)

    echo "Storage account resource ID : ${ACCOUNT_ID}"
    echo "Signed-in user object ID    : ${USER_ID}"
    echo ""

    # Role assignment is idempotent: re-running when the assignment already
    # exists returns "already exists" without error.
    az role assignment create \
        --role "Storage Blob Data Contributor" \
        --assignee "${USER_ID}" \
        --scope "${ACCOUNT_ID}" \
        --output table || {
            echo ""
            echo "  NOTE: Role assignment may already exist — this is expected on re-runs."
            echo "  Continuing..."
        }
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Upload robots.txt to $web root
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 6: Upload robots.txt to \$web (prevents Google/Bing indexing)"
echo "══════════════════════════════════════════════════════════════════════"
# Landing pages are "public-but-unindexed" during Shape A.
# robots.txt blocks search crawlers; WhatsApp/iMessage/Signal scrapers ignore
# robots.txt (they are link-preview fetchers, not indexers) — intended.
echo ""
if [[ -f "${ROBOTS_TXT}" ]]; then
    retry_on_rbac_lag "robots.txt uploaded after RBAC propagation" \
        az storage blob upload \
        --account-name "${STORAGE_ACCOUNT}" \
        --container-name "\$web" \
        --name "robots.txt" \
        --file "${ROBOTS_TXT}" \
        --content-type "text/plain; charset=utf-8" \
        --overwrite \
        --auth-mode login \
        --output table
else
    echo "  WARNING: ${ROBOTS_TXT} not found — skipping robots.txt upload."
    echo "  Create scripts/robots.txt and re-run this step."
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Print static website primary endpoint (landing page base URL)
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 7: Static website primary endpoint (base URL for landing pages)"
echo "══════════════════════════════════════════════════════════════════════"
echo ""
if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY-RUN] STATIC_URL=\$(az storage account show --name ${STORAGE_ACCOUNT} --resource-group ${RESOURCE_GROUP} --query 'primaryEndpoints.web' -o tsv)"
    echo "  [DRY-RUN] echo \"Landing page base URL: \$STATIC_URL\""
else
    STATIC_URL=$(az storage account show \
        --name "${STORAGE_ACCOUNT}" \
        --resource-group "${RESOURCE_GROUP}" \
        --query "primaryEndpoints.web" -o tsv)

    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  LANDING PAGE BASE URL (save this)                           ║"
    echo "║  ${STATIC_URL}"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  Per-book landing page URL pattern:"
    echo "  ${STATIC_URL}{slug}--{last-6-of-book_id}/"
    echo ""
    echo "  Example:"
    echo "  ${STATIC_URL}vigyan-bhairav-tantra--b7f3a2/"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: Verification commands
# ─────────────────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════════════════════════════"
echo " Step 8: Verification"
echo "══════════════════════════════════════════════════════════════════════"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    echo "  [DRY-RUN] Verification commands (run after setup completes):"
    echo ""
    echo "  # (a) Confirm book-workspaces container exists with private access"
    echo "  az storage container list \\"
    echo "      --account-name ${STORAGE_ACCOUNT} \\"
    echo "      --auth-mode login \\"
    echo "      --query \"[].{name:name, publicAccess:properties.publicAccess}\" \\"
    echo "      -o table"
    echo ""
    echo "  # (b) Confirm static website endpoint responds (expect HTTP 404 — correct)"
    echo "  STATIC_URL=\$(az storage account show --name ${STORAGE_ACCOUNT} \\"
    echo "      --resource-group ${RESOURCE_GROUP} \\"
    echo "      --query 'primaryEndpoints.web' -o tsv)"
    echo "  curl -s -o /dev/null -w \"HTTP %{http_code}\\n\" \"\${STATIC_URL}\""
    echo ""
    echo "  # (c) Confirm robots.txt is reachable"
    echo "  curl -s \"\${STATIC_URL}robots.txt\""
else
    echo "  (a) Containers on ${STORAGE_ACCOUNT}:"
    retry_on_rbac_lag "container verification succeeded after RBAC propagation" \
        az storage container list \
        --account-name "${STORAGE_ACCOUNT}" \
        --auth-mode login \
        --query "[].{name:name, publicAccess:properties.publicAccess}" \
        -o table

    echo ""
    echo "  (b) Static website endpoint response (expect 404 — means live):"
    if [[ -n "${STATIC_URL:-}" ]]; then
        curl -s -o /dev/null -w "  HTTP %{http_code}\n" "${STATIC_URL}" \
            || echo "  curl failed — endpoint may need 30 s to propagate"
    else
        STATIC_URL=$(az storage account show \
            --name "${STORAGE_ACCOUNT}" \
            --resource-group "${RESOURCE_GROUP}" \
            --query "primaryEndpoints.web" -o tsv)
        curl -s -o /dev/null -w "  HTTP %{http_code}\n" "${STATIC_URL}" \
            || echo "  curl failed — endpoint may need 30 s to propagate"
    fi

    echo ""
    echo "  (c) robots.txt content:"
    curl -s "${STATIC_URL}robots.txt" \
        || echo "  (robots.txt not yet reachable — check upload step above)"
fi

echo ""
echo "══════════════════════════════════════════════════════════════════════"
echo " Setup complete."
echo ""
echo " Next steps:"
echo "  1. Save the landing page base URL above to .squad/decisions.md"
echo "  2. Upload a test PDF: az storage blob upload \\"
echo "       --account-name ${STORAGE_ACCOUNT} \\"
echo "       --container-name ${CONTAINER_BOOK_WORKSPACES} \\"
echo "       --name 'test-book--000000/input/source.pdf' \\"
echo "       --file /path/to/your.pdf \\"
echo "       --auth-mode login"
echo "  3. Run the DB migration: alembic upgrade head"
echo "══════════════════════════════════════════════════════════════════════"
echo ""
