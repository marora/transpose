# Decision: Remove `keyvault_url` from Settings

**Author:** Chani
**Date:** 2026-04-21
**Status:** Proposed

## Context
`keyvault_url` was defined in Settings but never consumed by any service. Managed Identity provides direct access to Azure services (PostgreSQL via Entra auth, Blob Storage via DefaultAzureCredential, OpenAI via token provider). No Key Vault SDK client exists in the codebase.

## Decision
Remove the field. If Key Vault integration is needed in the future (e.g., for customer-managed encryption keys), re-add it with a corresponding service wrapper.

## Impact
- Operators no longer see a misleading `TRANSPOSE_KEYVAULT_URL` environment variable in config docs
- No functional change — the field was never read
