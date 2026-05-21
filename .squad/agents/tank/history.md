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

