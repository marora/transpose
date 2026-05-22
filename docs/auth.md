# Admin dashboard auth

Transpose protects `/admin/*` with Microsoft Entra ID bearer tokens.

This doc is checked in as a **template**. Environment-specific tenant and client IDs are referenced as `${ENTRA_TENANT_ID}` and `${ENTRA_CLIENT_ID}` and supplied via `.env` (see `.env.example`). The MSAL.js PKCE flow has no client secret, but tenant/client IDs are kept out of source so the repo is portable across dev/stage/prod and forks.

## Flow

1. Browser frontend uses **MSAL.js PKCE** with the `transpose-admin` app registration.
2. It requests delegated scope `api://transpose-admin/Dashboard.Read`.
3. aiohttp middleware on the existing Container App validates the bearer token against the tenant OpenID discovery + JWKS endpoints.
4. Only `/admin/*` is Entra-protected. Existing `/health`, `/ready`, `/translate`, and `/status/*` keep their current behavior.
5. No client secret is issued or required.

## App registration

- **Tenant ID:** `${ENTRA_TENANT_ID}`
- **Client ID:** `${ENTRA_CLIENT_ID}`
- **Scope / audience:** `api://transpose-admin/Dashboard.Read`
- **Issuer:** `https://login.microsoftonline.com/${ENTRA_TENANT_ID}/v2.0`
- **JWKS URI:** `https://login.microsoftonline.com/${ENTRA_TENANT_ID}/discovery/v2.0/keys`

Resolve the actual values for your environment from `.env` (local) or the
container app's environment configuration (deployed).

## Redirect URIs

Configure at least:
- `http://localhost:8000/admin/` for local development
- The deployed Container App's `/admin/` URL for each environment

After the first public admin deploy, add the externally reachable HTTPS `/admin/` redirect URI to the app registration.

## Provisioning

Use the idempotent helper:

```bash
scripts/provision-admin-app-registration.sh
```

It creates or updates the `transpose-admin` app registration, preserves the existing `Dashboard.Read` scope ID on re-runs, and never creates a client secret.
