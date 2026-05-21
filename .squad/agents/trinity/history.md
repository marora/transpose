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

