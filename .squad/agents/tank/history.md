# Tank — Cloud/Infra Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Idaho (Dune cast) — see .squad/agents/_alumni/idaho/history.md for accumulated knowledge

## Session History (Pre-2026-05-21)

**2026-05-20T23:19:30Z — Phase 1 Deliverables (T-1/T-2/T-3):** Workspace schema extension. Used dedicated columns (`license_status`, `provenance_source`, `license_history`) rather than nested JSONB for performance (indexed queries). Idempotent DDL with CHECK constraints named and guarded with `DO IF NOT EXISTS`. Inline self-test in migration validates constraint is present. Backfill strategy: `ILIKE 'http%'` to distinguish real URLs from blob URIs. Azure setup script: dry-run uses `run()` function wrapper; subscription-confirm step executes even in dry-run (read-only).

**2026-05-21T01:39:16Z — Azure RBAC Propagation Lag:** `az role assignment create` succeeds before Blob data-plane honors the role (typical 30s–2min, up to ~5min). Wrap first data-plane calls in retry helper (backoff: 15s, 30s, 60s, 60s, 60s). Fail fast on non-auth errors.

**2026-05-21T01:34:36Z — Azure CLI Flag Drift:** `--404-document` (current) vs. `--error-document-404-path` (stale). Always check `az ... -h` for installed version.

---

## Learnings (Active)

### 2026-05-21T12:17:57-04:00: Static Website is the public book surface; `output` stays private

**Pattern:** `output` and `source-pdfs` are internal pipeline containers even when they hold the final exported book. Public reading/downloading must go through Azure Static Website under `$web/<slug>/`, with a landing page plus public PDF/ePub assets.

**Operational rule:** If someone shares a raw `blob.core.windows.net/output/...` URL and the storage account has `allowBlobPublicAccess=false`, that is a usage bug, not a storage misconfiguration. Fix the publish path or copy the release artifacts into `$web/<slug>/`; do not relax account-level public access.

### 2026-05-21T13:45:28-04:00: Public-domain original scans should live at `$web/{slug}/source.pdf`

**Pattern:** When a book is safe to publish publicly, the reader-facing Original Scan link should target the static website path, not a private container. For Shiv Sutra, the source file already existed privately at `book-workspaces/shiv-sutra--ee92a4/input/source.pdf`; copying it to `$web/shiv-sutra/source.pdf` restored the TR-3 landing contract immediately.

**Operational rule:** Keep the filename stable as `source.pdf` on the public slug path. It mirrors the workspace convention (`input/source.pdf`), keeps manual repairs deterministic, and avoids exposing private-container URLs in the live landing page.

### 2026-05-21T14:19:30-04:00: Book-cost source of truth is DB-first, not `book_costs`

**Pattern:** For completed-or-resumed books, the durable source for true OpenAI/OCR cost is PostgreSQL operational data (`translations.prompt_tokens`, `translations.completion_tokens`, `books.page_count` / `pages`), not the summarized `book_costs` table.

**Why:** `CostTracker.persist()` runs only on the happy path after workspace completes. If a run crashes or fails a gate, `book_costs` can be empty or partial. Shiv Sutra proved this: `book_costs` kept only the final resume's 2 blob writes, while the real spend had to be reconstructed from DB rows plus logs/App Insights.

**Operational rule:** For ad-hoc cost forensics, query DB first, then use local logs/App Insights only to fill blob-ops and stage-timing gaps. If blob counts are reconstructed rather than durably stored, say so explicitly and point to issue #93.

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

---

## 2026-05-21T14:19:30.760-04:00: Shiv Sutra Cost Forensics — $12.13 Total Spend

**From:** Tank (cost investigation)  
**Context:** Manish asked "what did the Shiv Sutra e2e run cost?" Investigation traced spend through PostgreSQL + logs.

### True Cost Breakdown

| Component | Details | Cost |
|-----------|---------|------|
| OpenAI (GPT-4o) | 1,161,417 input + 255,580 output tokens | $9.64 |
| OCR (Doc Intelligence) | 249 pages | $2.49 |
| Blob storage | ~100 operations (reconstructed) | $0.00006 |
| **Total** | **Wall time: 10h 32m** | **$12.13** |

### Key Learning: `book_costs` Unreliable on Resume/Failure

`CostTracker.persist()` only fires on happy-path workspace completion. Shiv Sutra resumed from glossary after crash:
- `book_costs` table retained **only** the final resume's blob summary (2 writes)
- Real OpenAI + OCR spend lived in `translations`, `books.page_count`, `pages` tables (durable across all runs)

**Operational rule:** For cost forensics, query DB operational tables first; logs/App Insights second for blob ops; state confidence explicitly if reconstructed.

### Decisions Written + Filed

1. **Tank: Cost Telemetry Source of Truth** — merged into `.squad/decisions.md`
2. **Tank: Original Scan Publishing** — merged into `.squad/decisions.md`
3. **GitHub #93:** `cost_tracker` persistence gap — persist `book_costs` even on failed/resumed runs

### Related Files

- `.squad/log/2026-05-21T14-19-30Z-shiv-sutra-true-cost.md` — session log
- `.squad/orchestration-log/2026-05-21T14-19-30Z-tank-cost-telemetry.md` — investigation notes
- `.squad/decisions.md` — 2 new decisions appended

