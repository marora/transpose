# Tank — Infrastructure Dev History Archive

**Archive period:** Pre-2026-05-22 dated entries and learnings  
**Purpose:** Historical context for infrastructure decisions and investigations  
**See also:** `.squad/agents/tank/history.md` for current work

---

## Session History (Pre-2026-05-21)

2026-05-20T23:19:30Z — Phase 1 Deliverables (T-1/T-2/T-3): Workspace schema extension. Used dedicated columns (`license_status`, `provenance_source`, `license_history`) rather than nested JSONB for performance (indexed queries). Idempotent DDL with CHECK constraints named and guarded with `DO IF NOT EXISTS`. Inline self-test in migration validates constraint is present. Backfill strategy: `ILIKE 'http%'` to distinguish real URLs from blob URIs. Azure setup script: dry-run uses `run()` function wrapper; subscription-confirm step executes even in dry-run (read-only).

2026-05-21T01:39:16Z — Azure RBAC Propagation Lag: `az role assignment create` succeeds before Blob data-plane honors the role (typical 30s–2min, up to ~5min). Wrap first data-plane calls in retry helper (backoff: 15s, 30s, 60s, 60s, 60s). Fail fast on non-auth errors.

2026-05-21T01:34:36Z — Azure CLI Flag Drift: `--404-document` (current) vs. `--error-document-404-path` (stale). Always check `az ... -h` for installed version.

---

## Learnings from 2026-05-21

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

## Additional Phase 1 Work — 2026-05-20T23:10:06.050-04:00

Azure Storage + Landing Page Architecture (Morpheus + Niobe)

### Your Added Tasks (Phase 1 — Priority)

**T-1: Azure Storage Setup** (Copy-pasteable command sequence)
- Confirm active Azure subscription: `az account show`
- Create resource group: `transpose-rg` (eastus, idempotent)
- Create storage account: `transposebooks` (Standard_LRS, StorageV2, public access OFF, TLS1.2 min)
- Create private container: `book-workspaces` (public-access: off)
- Enable Static Website feature
- Assign `Storage Blob Data Contributor` role to your user identity
- Verify: containers list and static website endpoint works

**T-2: DB Migration — `license_status` + `metadata` JSONB** (Extends prior migration)
- Add columns to `books` table with CHECK constraints and defaults
- Backfill script: all existing rows get safe defaults
- Acceptance: status counts, check constraint presence, Dozer's DB integration tests pass

**T-3: Static Website `robots.txt`**
- Upload `robots.txt` to `$web/robots.txt` with deny-all content
- Prevents Google/Bing indexing; message app scrapers not affected (intentional)

---

## Cross-Agent Dependencies — 2026-05-21T05:11:39Z

Trinity Backfill CLI depends on `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` env var. Ensure this is set in all downstream Container App deployments.

---

## Azure Blob Containers Auto-Created — 2026-05-21T16:08:19Z

Shiv Sutra e2e run auto-created `output` and `source-pdfs` containers. Action item: add explicit pre-creation to `azure-setup.sh` so container creation is idempotent and documented.

---

## Shiv Sutra Cost Forensics — 2026-05-21T14:19:30.760-04:00

**Total spend:** $12.13 (OpenAI $9.64 + OCR $2.49 + Blob $0.00006)  
**Wall time:** 10h 32m

**Key learning:** `CostTracker.persist()` only fires on happy path. Durable cost source is PostgreSQL operational data, not `book_costs` table. This gap is tracked in issue #93.

**Decisions filed:**
1. Tank: Cost Telemetry Source of Truth
2. Tank: Original Scan Publishing

---

