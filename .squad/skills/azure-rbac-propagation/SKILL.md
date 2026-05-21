---
name: "azure-rbac-propagation"
description: "Handle Azure Entra RBAC propagation lag between control-plane role grants and Storage Blob data-plane authorization"
domain: "azure-storage, rbac, reliability"
confidence: "high"
source: "earned — Transpose Azure setup recovery, 2026-05-21T01:39:16.276-04:00"
---

## Context

Use this when a workflow grants Azure RBAC (for example `Storage Blob Data Contributor`) and then immediately performs `az storage blob ... --auth-mode login` or `az storage container ... --auth-mode login` operations.

Azure control-plane success does **not** mean the Blob data plane will honor the role immediately. Typical propagation is 30s–2min; fresh setups can occasionally take up to ~5min.

## Patterns

1. **Retry only auth-shaped failures.** Match messages such as:
   - `You do not have the required permissions needed to perform this operation`
   - `AuthorizationPermissionMismatch`
   - `This request is not authorized`
   - `Storage Blob Data Contributor`
   - HTTP 403 authorization responses
2. **Fail fast on non-auth errors.** Do not retry missing files, invalid arguments, or unrelated network/configuration failures.
3. **Use bounded backoff.** Good default: 6 attempts total with sleeps of `15s, 30s, 60s, 60s, 60s` after failed auth attempts.
4. **Make the wait explicit.** Print a message like `⏳ Waiting for RBAC role propagation… (attempt 2/6, sleeping 15s)`.
5. **Keep login auth as the default path.** Mention `--auth-mode key` only as a manual escape hatch; do not silently downgrade auth.

## Examples

```bash
retry_on_rbac_lag "robots.txt uploaded after RBAC propagation" \
  az storage blob upload \
  --account-name "$STORAGE_ACCOUNT" \
  --container-name '$web' \
  --name robots.txt \
  --file scripts/robots.txt \
  --auth-mode login \
  --overwrite
```

```bash
retry_on_rbac_lag "container verification succeeded after RBAC propagation" \
  az storage container list \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  -o table
```

## Anti-Patterns

- Retrying every failure blindly; this hides real bugs.
- Falling back to account keys automatically when login auth is the intended security model.
- Assuming `az role assignment create` completion means blob uploads will succeed immediately.
