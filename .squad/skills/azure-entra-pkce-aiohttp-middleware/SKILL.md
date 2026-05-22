---
name: "azure-entra-pkce-aiohttp-middleware"
description: "Protect aiohttp /admin/* routes with Entra ID bearer tokens for a PKCE SPA without introducing client secrets"
domain: "entra-id, aiohttp, admin-dashboard, azure-container-apps"
confidence: "high"
source: "earned — issue #98 on Transpose observability MVP, 2026-05-21T23:47:25-04:00"
---

## Context

Use this when a lightweight admin UI should be served from the same aiohttp app that exposes JSON routes, and the browser frontend authenticates with MSAL.js PKCE.

## Pattern

1. Register a single-tenant Entra app for the admin surface.
2. Expose delegated scope `Dashboard.Read` under an identifier URI such as `api://transpose-admin`.
3. Serve `/admin/` static files and `/admin/api/*` JSON routes from the existing aiohttp Container App.
4. Apply Entra bearer-token validation only to `/admin/*`; leave public probes and existing API-key routes alone.
5. Cache JWKS for ~5 minutes and force one refresh on unknown `kid`.

## Token validation rules

- Validate RS256 signature against Entra JWKS
- Validate issuer against `https://login.microsoftonline.com/<tenant>/v2.0`
- Validate expiry and `nbf`
- Accept either:
  - configured audience string `api://transpose-admin/Dashboard.Read`, or
  - real Entra access-token shape `aud=api://transpose-admin` plus `scp=Dashboard.Read`

## Why

Entra access tokens usually place the resource URI in `aud` and the delegated permission in `scp`, even when product discussions talk about a single combined “audience” string. Supporting both shapes avoids a brittle integration and leaves room to add future admin scopes without breaking the first one.

## Operational notes

- No client secret needed; PKCE is enough for the SPA
- Managed Identity is unrelated to token validation; keep it for data-plane access only
- Return `WWW-Authenticate: Bearer ...` on 401s so frontend and operators get a clear challenge
- Placeholder `/admin/api/test` route is a good smoke probe before the real dashboard API ships
