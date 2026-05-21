# Tank — Cloud/Infra Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Idaho (Dune cast) — see .squad/agents/_alumni/idaho/history.md for accumulated knowledge

## Learnings
(Recast from Idaho — Matrix universe. All prior knowledge preserved in alumni archive.)

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

