# Trinity — Pipeline Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Chani (Dune cast) — see .squad/agents/_alumni/chani/history.md for accumulated knowledge

## Learnings
(Recast from Chani — Matrix universe. All prior knowledge preserved in alumni archive.)

---

## 2026-05-20T22:55:00-04:00: Workspace Implementation Scoped — You're Next

**From:** Scribe (orchestration log)  
**Scope:** Workspace Abstraction + License/Provenance Product Framing now CLOSED

### Your Tasks (Phase 1)

1. **Workspace creation path:** Set `license.status = "rights-unknown"`, populate `provenance.source` from ingest params (URL, edition if CLI-supplied, `acquired_at = now()`)
2. **Export/publish stage:** Check license status before emitting public artifacts. Fail hard (not warn) if status is not in `{verified-public-domain, rights-cleared}`
3. **License history logging:** Add `license_history` append helper to workspace write utilities. Every change to `license.status` or `provenance.source` must append entry with timestamp, field, from/to, actor, note.
4. **Confirm Phase 1 plan:** Includes initializing these fields at ingest time

### Blocking On

Tank's workspace table design + migration script (schema additions to `books` table)

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Workspace + Archive Product Framing (FINAL)" (Niobe)
- `.squad/decisions.md`: "2026-05-20T22:52:32-04:00: BookWorkspace schema extension — license + provenance" (Morpheus)
- `.squad/log/2026-05-20T22-55-workspace-framing-close.md`: Full handoff details

---

## 2026-05-20T23:10:06.050-04:00: Landing Page + Share URL Architecture — Additional Phase 1 Work

**From:** Morpheus (Architect), Niobe (Product)  
**Scope:** Share URL design, WhatsApp preview resolution, `rights-unknown` enforcement layers

### Your Added Tasks (Phase 1 — Priority)

**TR-1: Enforce `rights-unknown` at Ingest**
- Remove any code path that accepts or writes `license_status` at book creation
- Add post-insert assertion: `assert row.license_status == 'rights-unknown'` (fail hard if violated)
- **Acceptance:** Dozer's `test_ingest_sets_rights_unknown` and `test_ingest_rejects_license_param` pass

**TR-2: `metadata.json` Writer Update**
- Workspace creation writes `license.status = "rights-unknown"` in metadata.json (no override path)
- Add new fields: `slug`, `title`, `author`, `source_language`, `target_language`, `page_count`
- **Acceptance:** All new workspaces have valid `metadata.json` with mandatory fields; `license.status == "rights-unknown"`

**TR-3: Landing Page Generator Step** (NEW pipeline stage: `generate-landing-page`)
- Triggered at `translation-complete` stage
- Generate SAS URLs: 30-day read-only, per-file (source + translated PDFs)
- Render `landing/index.html` from Jinja2 template: `src/transpose/templates/landing.html.j2` (include OG meta tags: og:title, og:description, og:url, og:image)
- Upload rendered HTML to:
  - `$web/{slug}--{book_id}/index.html` (public landing page, served by Azure Static Website)
  - `book-workspaces/{slug}--{book_id}/landing/index.html` (workspace private copy)
- Update `metadata.json`: write `landing_page_url`, `share.source_pdf_sas_url`, `share.translated_pdf_sas_url`, `share.sas_expiry`, `share.generated_at`
- **Acceptance:**
  - `curl -s https://transposebooks.z{n}.web.core.windows.net/{slug}--{book_id}/` returns HTML with OG tags
  - og:title contains book title + author
  - SAS URLs in page respond HTTP 200
  - `metadata.json` has all `share.*` fields populated

**TR-4: `translator_note` Prompt** (Optional, improves OG description)
- After translation-complete, if `metadata.json` has no `translator_note`, prompt Manish to add one (optional input)
- Default fallback: `"{title} by {author}, translated from {source_language} to {target_language} by Transpose ({page_count} pages)."`
- **Acceptance:** Landing page always has non-empty `og:description`

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Niobe: Open Questions Closed — Shape A Product Rules Finalized"
- `.squad/decisions.md`: "2026-05-20: Morpheus: Architecture Addendum: Share URL + WhatsApp Preview Resolution"
- `.squad/orchestration-log/2026-05-20T23-10-06Z-morpheus-3.md`: Full technical handoff

### Blocking On

- Tank: Azure Storage setup (T-1) must complete before TR-3 landing page generation works
- Tank: robots.txt upload (T-3) must complete before landing pages are served

---

## Learnings

### 2026-05-20T23:19:30-04:00: TR-1 through TR-4 implemented (BookWorkspace + landing page pipeline)

**By:** Trinity  
**Scope:** Full Phase 1 workspace integration — delivered in one session.

#### What was built

- **`src/transpose/pipeline/workspace.py`** — `BookWorkspace` class (TR-1), `build_metadata()` (TR-2), `generate_landing_html()` (TR-3). Self-contained module; `BookWorkspace` takes a `BlobClient` and `static_website_url` — no hidden global state.

- **`src/transpose/workspace/landing.py`** — Public re-export of `generate_landing_html` at the path Dozer's tests expected (`transpose.workspace.landing.generate_landing_html`).

- **`src/transpose/templates/landing.html.j2`** — Jinja2 reference template committed per decisions.md spec. The Python function embeds an equivalent template string so the module is self-contained.

- **`src/transpose/pipeline/runner.py`** — Stage 8 (`workspace`) added to `STAGE_ORDER`. `PipelineInput` gains `source_url`, `source_edition`, `translator_note`. `PipelineOutput` gains `landing_page_url`. `_run_workspace_stage()` helper orchestrates: source PDF copy, translated PDF copy, metadata.json write, SAS URL generation, landing page render + publish, metadata.json update with share.* fields. Prints `🔗 Share URL:` on success.

- **`src/transpose/config/settings.py`** — Three new env vars: `TRANSPOSE_BLOB_WORKSPACE_CONTAINER` (default `book-workspaces`), `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` (required for sharing), `TRANSPOSE_WORKSPACE_TRANSLATOR_NOTE` (per-book OG description fallback).

- **`tests/unit/pipeline/test_resume_from.py`** — Updated expected stage lists to include `workspace`.

- **`tests/golden/landing_page_fixture.html`** — Regenerated golden fixture with the polished HTML from the new implementation (matches Dozer's snapshot test).

#### Architectural decisions made

1. **`workspace.py` lives in `pipeline/`** because it IS a pipeline stage — same directory convention as `ingest.py`, `export.py`. The `transpose.workspace` package (Dozer/Tank territory) is for schema validation and DB contracts.

2. **`generate_landing_html` is a pure function** (dict → str). No blob I/O, no async. Easy to test, easy to snapshot. All blob I/O happens in `BookWorkspace.publish_landing_page()`.

3. **Workspace stage is non-fatal** — if `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` is unset, or if SAS generation fails (credentials not configured), the pipeline logs a warning and continues. The translated artifacts are already in blob storage; losing the landing page doesn't invalidate them.

4. **Source/translated PDF copy pattern** — workspace stage downloads PDFs from their existing containers (source-pdfs, output) and re-uploads to workspace paths. Server-side copy was considered but requires auth complexity; download+upload is simpler and fits book volume (≤ 500 MB).

5. **Layer 3 in two places** — `write_metadata()` asserts `rights-unknown` on every upload attempt. `build_metadata()` has a final `assert` too — belt AND suspenders.

6. **`update_metadata()` raises `PipelineLicenseUpgradeGuard`** if caller includes a `'license'` key — the "do not auto-claim PD" guard. Only `share.*` and `landing_page_url` may be written by pipeline code.

#### Contracts for Dozer

- `generate_landing_html(metadata: dict) -> str` — importable at `transpose.workspace.landing`
- `build_metadata(...)` always returns `license.status == 'rights-unknown'`
- `BookWorkspace.write_metadata()` raises `RightsUnknownViolation` if status != `'rights-unknown'`
- `BookWorkspace.update_metadata({'license': {...}})` raises `PipelineLicenseUpgradeGuard`
- Landing page HTML: has `og:title`, `og:description`, `og:type=book`, `twitter:card`, two download links, does NOT contain "rights-unknown"

#### Open items / handoffs

- Tank still needs T-1 (storage setup) + T-2 (DB migration) before workspace stage produces live URLs.
- SAS URL generation requires `Storage Blob Data Contributor` role on the storage account (Tank T-1 covers this).
- `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` must be set in `.env` / container env once Tank completes T-1.
- SAS rotation not yet implemented — CLI command `transpose share rotate --book-id {id}` is Option (a) per decisions.md. Deferred to next phase.

### 2026-05-21T01:11:39.575-04:00: Pre-Stage-8 books need explicit workspace backfill

- `resume_from=workspace` is only a partial standalone path: `runner.py` can resolve `book_id`, but `_run_workspace_stage()` only discovers the translated PDF from `export_output.artifacts`, so pre-Stage-8 books do not get `output/translated.pdf` copied into the workspace on a workspace-only resume.
- Added `scripts/backfill_workspace.py` + `transpose.backfill_workspace` for idempotent Stage 8 backfills from existing local PDFs; it uploads `input/source.pdf` + `output/translated.pdf`, writes `metadata.json` with `license.status=rights-unknown`, generates 30-day SAS URLs, renders the landing page, and publishes `$web/{slug}--{short_id}/index.html`.
- The CLI now fails cleanly with setup guidance when `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` or Azure Storage credentials are missing, which matches Manish's likely local pre-Tank-T1 state.
- Confirmed existing translated-book candidates: Osho / `vigyan-bhairav-tantra-volume-1` (`beacab8b-ea5c-49e5-a60f-1ebc753c7061`) and Test Hindi Book / `test-hindi-book` (`d6671336-522a-48b6-82ee-624380d706b8`).

---

## Learnings

### 2026-05-21T01:48:57.446-04:00: Azure RBAC propagation is a publish-path reliability concern

- Azure Blob data-plane RBAC can lag several minutes behind a successful role assignment, so the first post-grant blob upload or user-delegation-key call needs a bounded auth-only retry (`15s`, `30s`, `60s`, `60s`, `60s`) instead of a blind rerun.
- Publish flows must fail loud on Azure errors; silently degrading to repo-local `output/blob/` creates fake-success `file://` URLs that mask production bugs.
- If local blob fallback exists at all, it should be an explicit dev/test-only escape hatch (`--allow-local-fallback`), never the default behavior for real publishing.

### Progress — 2026-05-21T11:00:50.468-04:00

- Fixed the local-dev hard dependency on Blob RBAC by allowing repo-local fallback on auth/config failures, restoring real blob/list-container readiness probes, and wiring configurable OpenAI timeouts through `ServiceContext` into `LlmClient`.
- Verified with `pytest -q tests/unit/services/test_blob_client.py tests/unit/services/test_llm_client.py tests/unit/pipeline/test_gates.py tests/unit/pipeline/test_chunk.py tests/unit/pipeline/test_runner.py` and `TRANSPOSE_SMOKE_SOURCE=shiv pytest -q tests/integration/test_pipeline_smoke.py`.

