# 2026-05-20T22:55:00-04:00 — Workspace Framing Close & Implementation Handoff

**Session:** Workspace Abstraction + Archive + Audiobook Product Framing (CLOSED)  
**PM:** Niobe (PM, Claude Haiku 4.5)  
**Architecture:** Morpheus (Lead, Claude Sonnet 4.6)  
**Owner:** Manish  

---

## Session Outcome

✅ **Product framing CLOSED. Architecture extended. Ready for implementation handoff to Trinity (pipeline), Tank (storage), Dozer (tests).**

---

## What Was Decided

### 1. MVP Scope (Shape A) — BUILD NOW

**Personal translation workbench + private share mechanism**

- Manish translates heritage texts
- Artifacts live in workspace storage (book-workspaces/ hierarchy, metadata.json, input/ocr/translation/output/reports)
- License + provenance metadata tracks per-book judgment and source provenance
- Private artifact download links via signed blob URLs (no auth database yet)
- Private status dashboard showing pipeline progress + license status
- Shared URL mechanism for close colleagues/friends (TBD: signed URLs or static HTML listing)

**Success metric:** Manish translates a book, shares the translated PDF/ePub + glossary via private URL, retains full artifact lineage.

**What's explicitly out:** public archive site, audiobooks, multi-user accounts, formal review workflow, public metadata index, multi-channel distribution.

### 2. Shape B Gate (Future) — UNLOCK PER-BOOK

**Curated public heritage archive**

When: Manish has 3–5 books with `license.status ∈ {verified-public-domain, rights-cleared}` and decides archive is valuable.

What: Static or low-code site (GitHub Pages or small app) indexing books by title, author, language, tradition. Downloads from blob storage. Free, no accounts, no DRM.

Gate: Manish manually audits source PDF, updates `license.status`, marks book eligible for archive listing.

**Deferred:** Archive site design, audiobook generation, formal review, distribution (Spotify, Audible, archive.org, Hugging Face), automated rights research, reader analytics, monetization.

### 3. Schema Extensions (Mandatory)

Two new fields in workspace `metadata.json`:

#### `license` object
```jsonc
"license": {
  "status": "rights-unknown | claimed-public-domain | verified-public-domain | rights-cleared",
  "notes": "optional free text"
}
```
- Default at creation: `rights-unknown` (forces conscious upgrade)
- Mutable (all changes logged to `license_history`)

#### `provenance.source` object
```jsonc
"provenance": {
  "source": {
    "url": "string | null",
    "edition": "string",
    "acquired_at": "ISO 8601",
    "notes": "string | null"
  }
}
```
- All keys present at creation
- `url`, `notes` may be null
- `acquired_at` mandatory (defaults to ingest timestamp)

### 4. Promotion-Eligibility Rule

```
license.status ∈ { "verified-public-domain", "rights-cleared" }
```

→ Only these statuses eligible for Shape B archive listing.  
→ Enforced at storage layer (blob ACL), catalog layer (index filter), pipeline (export/publish gate).

### 5. Risk Posture

**Copyright uncertainty:** Manish owns the risk and the judgment call. He asserts antiquated spiritual texts are likely public domain and his translation is defensible. Workspace infrastructure documents his decisions per-book (auditable) but does not enforce external legal compliance. Legal verification deferred to per-book promotion decision.

**Modern editions:** `provenance.source` forces explicitness about which edition scanned. `license.status` forces per-book decision. Documented and auditable.

**Jurisdiction drift:** PD status varies by country (India, US, UK, EU). Manish aware; workspace allows per-book future clarification.

---

## Architecture Decisions Published

Both entries merged to `.squad/decisions.md`:

1. **2026-05-20: Workspace + Archive Product Framing (FINAL)** — Niobe  
2. **2026-05-20T22:52:32-04:00: BookWorkspace schema extension — license + provenance** — Morpheus

---

## Implementation Handoff

### Trinity (Pipeline Lead)

**Tasks:**
- Workspace creation path: set `license.status = "rights-unknown"`, populate `provenance.source` from ingest params
- Export/publish stage: check license status before emitting public artifacts; fail hard if ineligible
- Add `license_history` append helper to workspace write utilities
- Confirm Phase 1 plan includes initializing these fields at ingest time

**Blocking on:** Tank's workspace table design + migration script

### Tank (Storage / Infrastructure)

**Tasks:**
- Write DB migration: add `license_status TEXT` (with check constraint), `provenance_source JSONB`, `metadata JSONB` to `books` table
- Write backfill script for existing books: `license_status = 'rights-unknown'`, `provenance_source.url` from `source_blob_uri` (if URL-like), `acquired_at` from `books.created_at`
- Plan blob storage prefixes/lifecycle policies
- Confirm signed URL authentication for private share scenario works at scale
- Enforce blob ACL: workspace-private for non-eligible books (`rights-unknown`, `claimed-public-domain`)
- Align `book_workspaces` table design with new fields

**Blocking on:** None (architecture complete)

### Dozer (QA / Test)

**Tasks:**
- Unit test: workspace creation always produces `license.status = "rights-unknown"`
- Unit test: `provenance.source.acquired_at` is always set (never null) after creation
- Unit test: promotion gate returns false for `rights-unknown`, `claimed-public-domain`; true for `verified-public-domain`, `rights-cleared`
- Integration test: export/publish stage raises error (not warning) when license_status ineligible
- Regression test: mutation to `license.status` appends entry to `license_history`; does not silently overwrite
- DB constraint test: invalid `license_status` value is rejected
- Blob ACL test: private books don't leak via signed URLs

**Blocking on:** Tank's migration, Trinity's implementation

---

## Open Architecture Questions (For Niobe/Manish Follow-Up)

1. **`claimed-public-domain` visibility:** Should Shape A "close friends" share include `claimed-public-domain` books, or only `verified-public-domain`? Current rule keeps them fully private.

2. **`verified-public-domain` criteria:** Add structured sub-field for evidence (publication year, jurisdiction, rationale) vs. relying on free-text `license.notes`?

3. **`rights-cleared` workflow:** Where to store signed permission artifacts (e.g., `input/permission.pdf`)? Deferred but worth clarifying before Tank designs workspace layout.

4. **Multi-scan editions:** Can the same text exist in two workspaces (one `verified-public-domain`, one `claimed-public-domain`)? Current design assumes 1:1. Confirm.

---

## Quality Signals

✅ **PM framing coherent:** MVP (Shape A) is reviewable, achievable, and addresses Manish's stated needs without overcommitting.  
✅ **Architecture aligned:** Morpheus properly extends prior workspace decision; schema additions are additive, not breaking.  
✅ **Risk acknowledged:** Copyright uncertainty is named, owned by Manish, documented.  
✅ **Deferred clearly:** Archive site, audiobooks, formal review, distribution, analytics — all explicitly out of MVP scope.  
✅ **Handoff ready:** Implementation tasks are concrete, dependencies are clear, no ambiguity on who owns what.

---

## Next Phases

**Near-term (1–2 weeks):**
- Tank runs migration, backfill, blob ACL setup
- Trinity implements workspace creation, export gate, license_history logging
- Dozer writes and verifies tests

**Mid-term (2–4 weeks):**
- Manish ingests first books into Shape A (private workbench)
- Pipeline processes 3–5 books to completion
- Manish evaluates per-book license status, ready for manual promotion if desired

**Long-term (4+ weeks):**
- When 3–5 books reach Shape A completion + Manish judges at least 1–2 as `verified-public-domain` or `rights-cleared`, re-open Shape B framing (Niobe: archive site design, distribution strategy)
- If Shape B approved: implement static archive index, blob-backed downloads, optional secondary distribution

---

**Session closed:** 2026-05-20T22:55:00-04:00  
**Decisions archived:** `.squad/decisions.md`  
**Orchestration logs:** `.squad/orchestration-log/2026-05-20T22-55-{niobe,morpheus}.md`  
**Ready for: Phase 1 implementation (Trinity, Tank, Dozer)**

