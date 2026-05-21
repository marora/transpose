# Tank — Cloud/Infra Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Idaho (Dune cast) — see .squad/agents/_alumni/idaho/history.md for accumulated knowledge

## Learnings
(Recast from Idaho — Matrix universe. All prior knowledge preserved in alumni archive.)

### 2026-05-20T23:19:30-04:00: Phase 1 Deliverables — T-1/T-2/T-3

**Migration approach:** Used separate dedicated columns (`license_status TEXT`, `provenance_source JSONB`, `license_history JSONB`) rather than folding everything into `metadata JSONB` (Morpheus Option B). This enables indexed promotion-gate queries (`WHERE license_status IN (...)`) without JSON operator overhead. `metadata JSONB` is still added as the workspace contract carrier.

**Idempotent DDL pattern:** All `ALTER TABLE ... ADD COLUMN` statements use `ADD COLUMN IF NOT EXISTS`. CHECK constraint uses a named constraint (`chk_books_license_status`) with a `DO $$ IF NOT EXISTS` guard — safe on re-run against a partially-migrated DB.

**Inline self-test in migration:** Embedded a DO-block in the upgrade() that inserts an invalid `license_status` value and asserts a `check_violation` exception is raised. If the constraint is absent/malformed the migration fails at apply time, not silently post-deploy. This is the "SQL test" required by the task.

**Backfill strategy for `provenance_source.url`:** Used `ILIKE 'http%'` against `source_blob_uri` to distinguish real URLs from blob paths. Blob storage URIs (e.g. `wasbs://...`, internal refs) are set to `null`; HTTP(S) URLs are preserved.

**Azure setup script dry-run:** The `--dry-run` flag uses a `run()` shell function wrapper (echoes args instead of executing). The subscription-confirm step (Step 0) always executes even in dry-run — read-only, useful to confirm target before any changes.

**robots.txt placement:** `scripts/robots.txt` uploaded from `scripts/` alongside `azure-setup.sh` so the upload command has a local path without hardcoding. Script uses `SCRIPT_DIR` derived from `BASH_SOURCE[0]` for portability.

**Role assignment idempotency:** `az role assignment create` returns an error if the assignment already exists; script wraps it in `|| { echo NOTE; }` so re-runs don't abort on idempotent state.

**Static Website `--error-document-404-path`:** Used the correct Azure CLI flag name (not `--error-document`); the old CLI used `--404-document`. Verified with `bash -n` syntax check.

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
