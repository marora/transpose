# Dozer — Tester History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Thufir (Dune cast) — see .squad/agents/_alumni/thufir/history.md for accumulated knowledge

## Learnings
(Recast from Thufir — Matrix universe. All prior knowledge preserved in alumni archive.)

---

## 2026-05-20T22:55:00-04:00: Workspace Implementation Scoped — You're Next

**From:** Scribe (orchestration log)  
**Scope:** Workspace Abstraction + License/Provenance Product Framing now CLOSED

### Your Tasks (Phase 1)

1. **Unit tests:**
   - Workspace creation always produces `license.status = "rights-unknown"`
   - `provenance.source.acquired_at` is always set (never null) after creation
   - Promotion gate: returns false for `rights-unknown`, `claimed-public-domain`; returns true for `verified-public-domain`, `rights-cleared`

2. **Integration tests:**
   - Export/publish stage raises error (not warning) when license_status is ineligible
   - Blob ACL: private books don't leak via signed URLs

3. **Regression tests:**
   - Mutation to `license.status` appends entry to `license_history`
   - Does not silently overwrite; all mutations are logged

4. **DB constraint tests:**
   - Inserting a row with invalid `license_status` value is rejected
   - Check constraint is properly enforced

### Blocking On

- Tank's migration (DB schema in place)
- Trinity's implementation (workspace creation, export gate, license_history logging)

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Workspace + Archive Product Framing (FINAL)" (Niobe)
- `.squad/decisions.md`: "2026-05-20T22:52:32-04:00: BookWorkspace schema extension — license + provenance" (Morpheus)
- `.squad/log/2026-05-20T22-55-workspace-framing-close.md`: Full handoff details

