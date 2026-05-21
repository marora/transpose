# Tank — Cloud/Infra Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Idaho (Dune cast) — see .squad/agents/_alumni/idaho/history.md for accumulated knowledge

## Learnings
(Recast from Idaho — Matrix universe. All prior knowledge preserved in alumni archive.)

### 2026-05-21T12:17:57.347-04:00: Static Website is the public book surface; `output` stays private

**Pattern:** `output` and `source-pdfs` are internal pipeline containers even when they hold the final exported book. Public reading/downloading must go through Azure Static Website under `$web/<slug>/`, with a landing page plus public PDF/ePub assets.

**Operational rule:** If someone shares a raw `blob.core.windows.net/output/...` URL and the storage account has `allowBlobPublicAccess=false`, that is a usage bug, not a storage misconfiguration. Fix the publish path or copy the release artifacts into `$web/<slug>/`; do not relax account-level public access.

### 2026-05-21T13:45:28.928-04:00: Public-domain original scans should live at `$web/{slug}/source.pdf`

**Pattern:** When a book is safe to publish publicly, the reader-facing Original Scan link should target the static website path, not a private container. For Shiv Sutra, the source file already existed privately at `book-workspaces/shiv-sutra--ee92a4/input/source.pdf`; copying it to `$web/shiv-sutra/source.pdf` restored the TR-3 landing contract immediately.

**Operational rule:** Keep the filename stable as `source.pdf` on the public slug path. It mirrors the workspace convention (`input/source.pdf`), keeps manual repairs deterministic, and avoids exposing private-container URLs in the live landing page.

### 2026-05-21T01:39:16.276-04:00: Azure RBAC propagation lag on Storage data-plane

**Pattern:** `az role assignment create` can succeed several seconds before `az storage blob ... --auth-mode login` or `az storage container ... --auth-mode login` starts honoring the new role. Typical Azure Entra ID RBAC propagation to the Blob data plane is 30s–2min, occasionally up to ~5min.

**Operational fix:** After granting `Storage Blob Data Contributor`, wrap the first data-plane calls in a retry helper that retries only on authorization/permission failures with backoff (15s, 30s, 60s, 60s, 60s). Fail fast on non-auth errors so missing files / bad arguments / network issues do not get masked.

**Reuse note:** This is broad enough to justify a reusable squad skill because the same lag can hit first-run setup scripts, one-shot backfills, and pipeline publish stages.

### 2026-05-20T23:19:30-04:00: Phase 1 Deliverables — T-1/T-2/T-3

**Migration approach:** Used separate dedicated columns (`license_status TEXT`, `provenance_source JSONB`, `license_history JSONB`) rather than folding everything into `metadata JSONB` (Morpheus Option B). This enables indexed promotion-gate queries (`WHERE license_status IN (...)`) without JSON operator overhead. `metadata JSONB` is still added as the workspace contract carrier.

**Idempotent DDL pattern:** All `ALTER TABLE ... ADD COLUMN` statements use `ADD COLUMN IF NOT EXISTS`. CHECK constraint uses a named constraint (`chk_books_license_status`) with a `DO $$ IF NOT EXISTS` guard — safe on re-run against a partially-migrated DB.

**Inline self-test in migration:** Embedded a DO-block in the upgrade() that inserts an invalid `license_status` value and asserts a `check_violation` exception is raised. If the constraint is absent/malformed the migration fails at apply time, not silently post-deploy. This is the "SQL test" required by the task.

**Backfill strategy for `provenance_source.url`:** Used `ILIKE 'http%'` against `source_blob_uri` to distinguish real URLs from blob paths. Blob storage URIs (e.g. `wasbs://...`, internal refs) are set to `null`; HTTP(S) URLs are preserved.

**Azure setup script dry-run:** The `--dry-run` flag uses a `run()` shell function wrapper (echoes args instead of executing). The subscription-confirm step (Step 0) always executes even in dry-run — read-only, useful to confirm target before any changes.

**robots.txt placement:** `scripts/robots.txt` uploaded from `scripts/` alongside `azure-setup.sh` so the upload command has a local path without hardcoding. Script uses `SCRIPT_DIR` derived from `BASH_SOURCE[0]` for portability.

**Role assignment idempotency:** `az role assignment create` returns an error if the assignment already exists; script wraps it in `|| { echo NOTE; }` so re-runs don't abort on idempotent state.

**Static Website `--404-document`:** Azure CLI now expects `--404-document` for Static Website error pages; `--error-document-404-path` is stale and fails with `unrecognized arguments`. Verified via `az storage blob service-properties update -h` and `bash -n` syntax check.

### 2026-05-21T01:34:36.290-04:00: Azure CLI flag drift gotcha

**Static Website 404 flag drift:** `az storage blob service-properties update` currently accepts `--404-document`, not `--error-document-404-path`. When recovering a failed rerun, prefer checking `az ... -h` for the installed CLI version instead of relying on older command snippets.

---

## 2026-05-20T22:55:00-04:00: Workspace Implementation Scoped — You're Next

**From:** Scribe (orchestration log)  
**Scope:** Workspace Abstraction + License/Provenance Product Framing now CLOSED

### Your Tasks (Phase 1)

1. **DB Migration:** Add three columns to `books` table:
   - `license_status TEXT NOT NULL DEFAULT 'rights-unknown'` (with check constraint: only `rights-unknown`, `claimed-public-domain`, `verified-public-domain`, `rights-cleared`)
   - `provenance_source JSONB` (source object: url, edition, acquired_at, notes)
   - `metadata JSONB NOT NULL DEFAULT '{}'` (workspace contract)

2. **Backfill script:** For all existing books:
   - `license_status = 'rights-unknown'`
   - `provenance_source.url` ← backfill from `books.source_blob_uri` (if URL-like, else null)
   - `provenance_source.edition` ← null (must be filled manually per book later)
   - `provenance_source.acquired_at` ← `books.created_at` as proxy
   - `provenance_source.notes` ← null

3. **Blob storage policy:** Enforce workspace-private ACL for non-eligible books (license_status NOT IN `{verified-public-domain, rights-cleared}`)

4. **Workspace table design:** Align `book_workspaces` table with new `metadata`, `license_status`, `provenance_source` fields

5. **Signed URL auth:** Confirm private share scenario works at scale (Manish URL-authenticates download)

### Blocking On

None — architecture is complete. You can start immediately.

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Workspace + Archive Product Framing (FINAL)" (Niobe)
- `.squad/decisions.md`: "2026-05-20T22:52:32-04:00: BookWorkspace schema extension — license + provenance" (Morpheus)
- `.squad/log/2026-05-20T22-55-workspace-framing-close.md`: Full handoff details

---

## 2026-05-20T23:10:06.050-04:00: Azure Storage + Landing Page Architecture — Additional Phase 1 Work

**From:** Morpheus (Architect), Niobe (Product)  
**Scope:** Azure Blob setup, static website hosting, `rights-unknown` enforcement at DB layer

### Your Added Tasks (Phase 1 — Priority)

**T-1: Azure Storage Setup** (Copy-pasteable command sequence in `.squad/decisions.md` Morpheus decision, Section A)
- Confirm active Azure subscription: `az account show`
- Create resource group: `transpose-rg` (eastus, idempotent)
- Create storage account: `transposebooks` (Standard_LRS, StorageV2, public access OFF, TLS1.2 min)
- Create private container: `book-workspaces` (public-access: off)
- Enable Static Website feature: `az storage blob service-properties update --static-website --index-document index.html`
- Assign `Storage Blob Data Contributor` role to your user identity
- Verify: `az storage container list` shows `book-workspaces` with privateAccess; `curl` to static website endpoint returns 404 (correct — means live)
- **Acceptance:** Steps 7–8 succeed; base URL noted and saved to `.squad/decisions.md`

**T-2: DB Migration — `license_status` + `metadata` JSONB** (Extends prior migration from 2026-05-20T22:55)
- Add columns to `books` table:
  - `license_status TEXT NOT NULL DEFAULT 'rights-unknown' CHECK (license_status IN ('rights-unknown', 'claimed-public-domain', 'verified-public-domain', 'rights-cleared'))`
  - `metadata JSONB` (for landing page + share data; schema in Morpheus decision Section D)
  - `provenance_source JSONB` (source URL, edition, acquired_at — from prior decision)
- Backfill script: all existing rows get `license_status = 'rights-unknown'`, `metadata = '{}'::jsonb`, `provenance_source = '{}'::jsonb`
- **Acceptance:** 
  - `SELECT license_status, count(*) FROM books GROUP BY 1` → exactly one row: `rights-unknown | N`
  - `\d books` shows check constraint and defaults
  - Dozer's DB integration tests pass (T-2 test, constraint test)

**T-3: Static Website `robots.txt`**
- Upload `robots.txt` to `$web/robots.txt` with content:
  ```
  User-agent: *
  Disallow: /
  ```
- Prevents Google/Bing indexing; WhatsApp/iMessage/Signal scrapers not affected (intended)
- **Acceptance:** `curl https://transposebooks.z{n}.web.core.windows.net/robots.txt` returns 200 with correct content

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Niobe: Open Questions Closed — Shape A Product Rules Finalized"
- `.squad/decisions.md`: "2026-05-20: Morpheus: Architecture Addendum: Share URL + WhatsApp Preview Resolution"
- `.squad/orchestration-log/2026-05-20T23-10-06Z-morpheus-3.md`: Full technical handoff

### Blocking On

None — architecture complete. Start immediately.

### Unblocks

- Trinity: TR-3 landing page generation (needs Blob endpoint + static website URL)
- Dozer: All DB constraint tests


---

## 2026-05-21T05:11:39Z: Cross-Agent Note — Trinity Backfill CLI Dependency

**From:** Scribe (session log)  
**Context:** Trinity-1 built backfill_workspace.py + CLI for one-shot publishing of already-translated books.

**Your Output Used:**
- `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` env var must be set in deployment. Trinity's backfill CLI requires this; if unset, warnings + skip workspace stage (non-fatal).

**Routing:**
- Tank: If not already printed by your `azure-setup.sh`, ensure `TRANSPOSE_BLOB_STATIC_WEBSITE_URL=https://transposebooks.z{n}.web.core.windows.net` is passed to all downstream Container App deployments.

**See also:** `.squad/orchestration-log/2026-05-21T05-11-39Z-trinity-1-backfill.md`

---

## 2026-05-21T16:08:19Z: Azure Blob Containers Auto-Created During Shiv Sutra Run

**From:** Trinity (session completion)  
**Context:** Shiv Sutra e2e pipeline completed successfully; artifacts published to Azure

### Containers Created Mid-Run

During shiv sutra execution, Trinity auto-created two Azure Blob containers that were not pre-provisioned in azure-setup.sh:
- **`output`** container — received exported artifacts (Shiv_Sutra.epub 275KB, Shiv_Sutra.pdf 1.38MB)
- **`source-pdfs`** container — may have been used for intermediate pipeline artifacts

### Action Item for Tank

Flag in `azure-setup.sh`: Add explicit pre-creation of `output` and `source-pdfs` containers so:
1. Container creation is idempotent and documented
2. ACLs and retention policies can be set upfront (not inferred post-hoc)
3. Next book runs don't require mid-run container auto-creation

### Related Files
- `.squad/orchestration-log/2026-05-21T16-08-trinity.md` — full Trinity context
- Shiv Sutra artifacts in Azure `output` container

