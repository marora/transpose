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

---

## 2026-05-20T23:10:06.050-04:00: License + Landing Page Tests — Additional Phase 1 Work

**From:** Morpheus (Architect), Niobe (Product)  
**Scope:** Four-layer `rights-unknown` enforcement tests, landing page HTML validation, schema validation

### Your Added Tasks (Phase 1 — Priority)

**D-1: License Constraint Tests** (Four-layer enforcement: DB, app, metadata, tests)

Must write and maintain all five tests — they are binding:

| Test | Type | Assertion |
|------|------|-----------|
| `test_ingest_sets_rights_unknown` | Unit | `ingest_book(...)` → `book.license_status == 'rights-unknown'` |
| `test_ingest_rejects_license_param` | Unit | `ingest_book(..., license_status='claimed-public-domain')` raises `TypeError` (param doesn't exist) |
| `test_db_default_is_rights_unknown` | Integration | Raw SQL `INSERT INTO books (...) VALUES (...)` omitting `license_status` → row has `license_status = 'rights-unknown'` |
| `test_db_check_constraint` | Integration | Raw SQL `INSERT INTO books (..., license_status='made-up')` raises `IntegrityError` |
| `test_metadata_json_default` | Unit | Workspace creation writes `metadata.json` with `license.status == "rights-unknown"` |

- **Acceptance:** All five tests pass; D-1 tests written before Tank T-2 and Trinity TR-1 merge

**D-2: Landing Page Tests**

| Test | Assertion |
|------|-----------|
| `test_landing_page_contains_og_title` | Rendered HTML has `<meta property="og:title">` with correct content (book title + author) |
| `test_landing_page_contains_og_description` | Has `<meta property="og:description">` with translator_note or fallback |
| `test_landing_page_sas_urls_present` | HTML has source and translated PDF SAS URL links (non-empty) |
| `test_sas_url_readable` | Integration: generated SAS URL responds HTTP 200 with PDF content |

- **Acceptance:** All tests pass in CI; landing page generator (TR-3) validates via these tests

**D-3: `metadata.json` Schema Validation**

- Write schema validator (pydantic or jsonschema) for `metadata.json` covering mandatory-before-share fields: `title`, `author`, `landing_page_url`, `source_language`, `target_language`, `page_count`, `slug`, `share.source_pdf_sas_url`, `share.translated_pdf_sas_url`, `share.sas_expiry`, `share.generated_at`
- Validate in unit test against fixture and freshly created workspace
- **Acceptance:** Schema validator rejects `metadata.json` missing mandatory fields; passes on valid workspace metadata

### Related Decisions

- `.squad/decisions.md`: "2026-05-20: Niobe: Open Questions Closed — Shape A Product Rules Finalized"
- `.squad/decisions.md`: "2026-05-20: Morpheus: Architecture Addendum: Share URL + WhatsApp Preview Resolution"
- `.squad/orchestration-log/2026-05-20T23-10-06Z-morpheus-3.md`: Full technical handoff

### Blocking On

- Tank: T-2 (DB schema in place before D-1 integration tests can run)
- Trinity: TR-1, TR-2, TR-3, TR-4 (implementation before D-1, D-2, D-3 can validate)

### Unblocks

- Release readiness: All three agents can validate Phase 1 complete once Dozer tests pass

