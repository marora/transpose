# Skill: Auth-Protected Static + Dynamic API Dashboard on Azure

## When to Use

Single-operator (or small-team) dashboard that needs:
- Authentication (not public, not IP-allowlist)
- Live data from a database (Postgres, CosmosDB, etc.)
- Static frontend (HTML/JS/CSS)
- Zero additional Azure resources beyond what already exists

## Pattern

**Serve both static files and API routes from an existing Container App.**

```
Container App (already running)
├── /admin/              → static HTML/JS/CSS (aiohttp/FastAPI static file handler)
├── /admin/api/*         → JSON API routes (same app, same DB pool)
└── /health, /api/*      → existing routes (unchanged)
```

### Auth Layer

1. Register an Entra ID app (single-tenant, confidential client)
2. Frontend: MSAL.js PKCE flow → acquires access token
3. Backend: middleware validates bearer token (signature + audience + issuer + expiry) via Entra JWKS
4. Apply auth middleware ONLY to `/admin/*` routes — existing routes stay on their own auth (API key, etc.)

### Why This Over Alternatives

| Alternative | Problem |
|-------------|---------|
| Azure Front Door + OIDC | $35+/month, DNS/cert complexity, overkill for 1 user |
| Azure Static Web Apps | Replaces existing `$web/` blob hosting; EasyAuth less flexible |
| Separate Container App | Double the compute cost, double the deployment |
| IP allowlist on blob | Static HTML can't query a database |

### Cost

$0 additional/month. Entra app registration is free. Container App already runs. Postgres already runs.

### Constraints

- Dashboard availability = Container App availability (acceptable for operator tooling)
- Static assets are not CDN-cached (irrelevant for 1–5 users)
- If multi-tenant later: front with Azure CDN or move to Static Web Apps at that point

## Example File Structure

```
web/admin/
├── index.html    # MSAL login + SPA shell
├── app.js        # API calls + DOM rendering
└── style.css

src/app/
├── auth_middleware.py    # Entra token validation
├── dashboard_api.py      # /admin/api/* route handlers
└── main.py               # Mount static + API routes
```

## References

- Microsoft identity platform: https://learn.microsoft.com/en-us/entra/identity-platform/
- MSAL.js browser: https://github.com/AzureAD/microsoft-authentication-library-for-js
- aiohttp static files: https://docs.aiohttp.org/en/stable/web_advanced.html#static-file-handling
