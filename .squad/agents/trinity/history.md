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

