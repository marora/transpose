---
name: "static-website-book-downloads"
description: "Publish public book landing pages and downloadable PDF/ePub assets via Azure Static Website while keeping raw blob containers private"
domain: "azure-storage, static-website, publishing"
confidence: "high"
source: "earned — Shiv Sutra public access fix, 2026-05-21T12:17:57.347-04:00"
---

## Context
Use this when a translated book must be downloadable by URL without opening up the raw `output` container. In Transpose, account-level blob public access stays disabled and the public surface is Azure Static Website (`$web`).

## Pattern
1. Keep internal pipeline containers private:
   - `source-pdfs`
   - `output`
   - `book-workspaces`
2. Enable Static Website on the storage account.
3. Publish the reader-facing surface to `$web/<slug>/`:
   - `index.html` (or `landing.html`)
   - translated PDF
   - translated EPUB
   - optional `metadata.json`, cover image, OG assets
4. Share only the Static Website URL, e.g. `https://<account>.z<N>.web.core.windows.net/<slug>/`.

## Required configuration
- `TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL=https://<account>.blob.core.windows.net`
- `TRANSPOSE_BLOB_STATIC_WEBSITE_URL=https://<account>.z<N>.web.core.windows.net/`

## Anti-patterns
- Sharing `https://<account>.blob.core.windows.net/output/...` directly.
- Enabling account-level public blob access to make `output` downloads work.
- Treating `PublicAccessNotPermitted` as a reason to weaken storage security.

## Operational notes
- Use `--auth-mode login` / Managed Identity for all `az storage ...` uploads and copies.
- `scripts/azure-setup.sh` must pre-create `source-pdfs`, `output`, and `book-workspaces`, and must print the Static Website endpoint for downstream app config.
- If a landing page exists but its download buttons are dead, verify the HTML `href` values before blaming Storage ACLs.
