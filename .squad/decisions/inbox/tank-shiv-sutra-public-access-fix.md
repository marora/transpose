# 2026-05-21T12:17:57.347-04:00 — Shiv Sutra public access fix

## Requested by
Manish

## Summary
Manish opened the raw Azure Blob URL for `output/Shiv_Sutra.pdf` and received `PublicAccessNotPermitted`. That storage-account setting is correct: `transposebooks` has account-level public blob access disabled, and `output` is an internal pipeline container.

## Diagnosis
- `transposebooks` is healthy: `allowBlobPublicAccess=false`, Static Website endpoint is `https://transposebooks.z13.web.core.windows.net/`.
- Required containers now exist: `$web`, `book-workspaces`, `output`, `source-pdfs`.
- Shiv Sutra workspace artifacts existed under `book-workspaces/shiv-sutra--ee92a4/` and a public landing page existed at `$web/shiv-sutra--ee92a4/index.html`.
- The local `.env` already had `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` set, so this was **not** a local env-missing skip.
- The deployed Container App `transpose-dev-app` was missing `TRANSPOSE_BLOB_STATIC_WEBSITE_URL`; I set it to its storage account’s website endpoint for drift reduction.
- Root cause for the broken user experience: Trinity’s export artifacts were in private `output`, but Manish was given the raw blob URL instead of a Static Website URL. Separately, the existing slug+id landing page had dead `href="#"` buttons because SAS generation failed; filed as issue #91.

## Immediate fix applied
I treated this as **Path B**: artifacts existed, but the public website path Manish needed did not.

Published the following to Azure Static Website (`$web/shiv-sutra/`):
- `index.html`
- `landing.html`
- `Shiv_Sutra.pdf`
- `Shiv_Sutra.epub`
- `metadata.json`

Verified public HTTP 200 for:
- `https://transposebooks.z13.web.core.windows.net/shiv-sutra/`
- `https://transposebooks.z13.web.core.windows.net/shiv-sutra/Shiv_Sutra.pdf`
- `https://transposebooks.z13.web.core.windows.net/shiv-sutra/Shiv_Sutra.epub`

## Prevention changes
- `scripts/azure-setup.sh`
  - pre-creates `source-pdfs`, `output`, and `book-workspaces`
  - keeps Static Website enablement explicit
  - prints `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` for local/app config
- Added `.env.example` documenting `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` derivation.
- Wired `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` into Container App IaC (`infra/modules/container-app.bicep`, `infra/main.bicep`).
- Extended storage IaC to create `book-workspaces` and output the Static Website endpoint.
- Updated `infra/scripts/remediate-env-vars.sh` so env drift cleanup knows about `TRANSPOSE_BLOB_STATIC_WEBSITE_URL`.

## Follow-up
- Issue #91: `Workspace publish generates blank download links when SAS generation fails`
  - https://github.com/marora/transpose/issues/91
- We still need a code-level fix so the pipeline cannot publish a landing page with dead download buttons.
