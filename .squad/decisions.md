# Transpose Squad Decisions

Canonical ledger of product, architecture, and policy decisions. Merged from inbox entries, deduplicated, and archived. Oldest entries first.

---

## 2026-04-25: Osho Editorial Gap Analysis R1

**Author:** Stilgar (Editorial/QA)  
**Type:** Quality Gate / Publication Readiness  
**Status:** DECIDED

Completed programmatic editorial gap analysis comparing the source Hindi PDF (95 pages, 55K words) against the translated English PDF (107 pages, 52K words). **Found 15 issues: 6 P0-blockers, 4 P1-high, 3 P2-medium, 2 P3-low.**

### Publication Verdict
**NOT READY FOR PUBLICATION.** The translated output cannot be released in its current state.

### Critical P0 Blockers (Must Fix)
1. ~2,900 Devanagari tokens of untranslated Hindi on pages 40–41, 82–83, 91–92 — raw OCR text passed through to output
2. `[Original text — translation unavailable]` failure markers visible on pages 40 and 81
3. All 23 source images stripped — zero images in translated output
4. PDF metadata empty — no title, author, subject fields
5. Method 4 entirely missing from ToC and body text
6. Word count ratio 0.94× (expected 1.2–1.5×) — confirms systemic content loss of 17K–34K words

### Recommended Actions
1. Translate stage: Re-run failed chunks with fallback prompts; add content filter bypass for religious/cultural text
2. Export stage: Add failure marker scanning gate — reject any PDF containing `[Original text`
3. Assembly stage: Add image pass-through pipeline; fix ToC deduplication; verify method numbering sequence
4. Export stage: Set PDF metadata; add copyright template page; add running headers via CSS `@page`

**Full Report:** `.squad/quality/osho-editorial-gap-analysis-r1.md`

**Relates To:** Issues #34, #39, #59, #60

---

## 2026-04-25: Osho VBT Vol 1 Export (Completed)

**Author:** Chani (Pipeline Dev)  
**Date:** 2026-04-25  
**Status:** COMPLETED

The Osho Vigyan Bhairav Tantra Volume 1 book (book_id `beacab8b-ea5c-49e5-a60f-1ebc753c7061`) completed all pipeline stages — 95 pages OCR'd, 97/97 chunks translated, 118 glossary terms extracted, 23 chapters assembled.

### Results
- **All 5/5 quality gates PASSED**: OCR sanity, translation completeness, glossary integrity, document structure, artifact availability
- **ePub**: `Osho_VBT_translated.epub` — 127 KB (129,058 bytes)
- **PDF**: `Osho_VBT_translated.pdf` — 1,010 KB (1,033,566 bytes)
- **Validation report**: `osho-validation-report.json`

### Artifact Archival Recommendation
These root-level demo artifacts should migrate to workspace-scoped blob storage as per 2026-05-20 workspace abstraction decision (see below). Keep one copy as repo fixture for CI/documentation; remove duplicates and obsolete versions from repo root.

---

## 2025-07-18: Osho VBT Translation — Publication Readiness R1

**Author:** Irulan (Publisher/Editor)  
**Date:** 2025-07-18  
**Status:** DECIDED

### Decision
**FAIL — Fix and Reship.** The Osho Vigyan Bhairav Tantra Volume 1 translation is not approved for publication.

### 4 P0 Blockers
1. **Garbled glossary** — 18 corrupted Devanagari characters across 12+ entries (font embedding / source data issue)
2. **3 untranslated chunks** — raw Hindi + `[Original text — translation unavailable]` markers on pages 41, 82, 92
3. **TOC duplicates** — Vachan-5 (3×) and Vachan-9 (4×) still duplicated despite reported fix
4. **Gurmukhi contamination** — "amrit" glossary entry in Punjabi script instead of Devanagari

### What Improved
- PDF metadata ✅ populated
- Copyright page ✅ present in PDF
- Core translation quality is solid across 22 methods

### Required for R2
- Fix all 4 P0 blockers
- Address P1 items (running headers, ePub copyright, missing images disclosure)
- Re-export and submit for Irulan R2 review

### Impact
- **Chani:** Fix glossary source data (Gurmukhi→Devanagari, garbled chars), fix TOC dedup
- **Stilgar:** Verify pipeline fix for untranslated chunk handling
- **Thufir:** Add test assertions for TOC uniqueness and glossary script validation

**Full Review:** `.squad/quality/osho-irulan-review-r1.md`

---

## 2025-07-25: Osho VBT Visual QA R1

**Author:** Thufir (Tester/QA)  
**Date:** 2025-07-25  
**Type:** QA Finding — Publication Readiness  
**Status:** DECIDED

Visual and structural QA of `Osho_VBT_translated.pdf` vs source Hindi PDF reveals **3 P0 blockers** preventing publication:

1. **Methods 18–23 are missing** — 6 of 22 discourse chapters (~28% of content) absent from translated output
2. **3 passages left untranslated** with `[Original text — translation unavailable]` markers and raw Hindi
3. **All 23 source images missing** — zero images carried over to translated PDF

Additionally: blank PDF metadata (P1), stale/duplicate TOC Vachan entries (P1), one Devanagari glyph mapping error (P2), and 3 high-density pages that may have formatting collapse (P2).

Positive findings: word ratio is 0.944 (healthy), cultural terms correctly preserved in glossary, zero markup artifacts, zero replacement characters, consistent font stack.

### Recommendation
Block publication. Address the 3 P0s before next QA round. P1s should be fixed concurrently.

**Full Report:** `.squad/quality/osho-visual-qa-r1.md`  
**Raw Data:** `.squad/quality/osho-qa-data-r1.json`

---

## 2026-05-20: Product Manager Role Added to Team

**Author:** Manish (via Squad Coordinator)  
**What:** Niobe joined as Product Manager.
**Why:** Team had architecture, pipeline, infra, test, and editorial roles but no product/strategy lens. Manish was carrying PM work himself. Capability-expansion requests (workspace abstraction, public archive, audiobooks) were being answered architecturally without first framing audience and outcome.

### Routing Change
New "Product framing & strategy" entry added to routing.md as the first row. "Scope & priorities" routes to Niobe (was Morpheus). "Architecture trade-offs" stays with Morpheus.

### Niobe's Mandate
- **Owns:** problem framing, audience definition, success criteria, MVP/scope cuts, prioritization
- **First task:** Product framing for the workspace abstraction question (from Morpheus decision 2026-05-20 below). **Before any build, Niobe frames:** who reads/uses the workspace? Public archive or internal tool? What's the success metric?
- **Process:** "Frame before build" — every capability request gets a one-pass product brief before architecture/implementation starts.

**Charter:** `.squad/agents/niobe/charter.md`  
**History:** `.squad/agents/niobe/history.md`

---

## 2026-05-20: Book Workspace Abstraction + Storage Strategy (Proposed)

**Author:** Morpheus (Architecture)  
**Date:** 2026-05-20  
**Status:** PROPOSED (gated on Niobe product framing)  
**Prerequisite:** Product framing (Niobe — first task)

### Decision
Introduce a first-class **Book Workspace** abstraction for every translation. Treat the workspace as a storage-backed object with metadata + artifact manifest; a folder/object-prefix layout is its concrete representation, not the core domain model.

Use a **hybrid storage strategy**:
- **Git repo:** source code, schemas/contracts, small metadata snapshots, and lightweight reviewable reports only.
- **Azure Blob Storage / ADLS Gen2:** original PDFs, exported PDFs/ePubs, OCR raw/intermediate artifacts, extracted images, future audiobook chapters, and other large binaries.

If a public archive is needed, publish through a **static catalog/index** (GitHub Pages or small web app) that links to Blob-hosted artifacts. Do not use the repo itself as the binary archive.

### Why
Current Transpose architecture is book-centric but artifact-fragmented:
- `books` is the root record for identity/status.
- Stage outputs persist across `pages`, `chunks`, `translations`, `glossaries`, `manuscripts`, `pipeline_state`, and `pipeline_jobs`.
- Blob storage already holds source and exported artifacts in production paths.
- Repo-root files and validation scripts currently act as ad hoc local artifact storage.

That means the system already has persistence primitives, but no coherent per-book workspace boundary for all assets and metadata.

### Workspace Shape
Recommended logical layout:
```text
book-workspaces/
  {book_slug}--{book_id}/
    metadata.json
    input/
      source.pdf
      source-url.txt
      checksums.json
    ocr/
      pages/
      page-images/
      cover.png
      quality-report.json
    translation/
      chunks/
      translations/
      glossary.json
      manuscript.json
    output/
      translated.epub
      translated.pdf
    audio/
      chapters/
      manifest.json
    reports/
      validation-report.json
      human-review.json
      editorial-notes.json
```

### Metadata Contract
`metadata.json` should include at minimum:
- `workspace_id`, `book_id`, `slug`, `title`, `author`
- `source_language`, `target_language`
- `source_url`, `source_hash_sha256`
- `status`, `pipeline_version`
- `created_at`, `updated_at`, `published_at`
- `artifact_manifest` (logical path + checksum + size + media type)

### Naming + Identity
- Canonical identifier: **database `book_id` UUID**
- Human-friendly prefix: **slugified title**
- Workspace path form: **`{slug}--{book_id}`**
- If ISBN exists, keep it in metadata; do **not** use it as primary key (titles collide, ISBN often absent)

### Immutability Rules
**Immutable inputs:**
- `input/source.pdf`
- `input/source-url.txt`
- `input/checksums.json`

**Derived but append/versioned:** OCR page JSON, chunk/translation intermediates, glossary/manuscript snapshots, reports, exported outputs, audio assets

Never mutate the original source artifact in place. Derived artifacts may be regenerated but should either overwrite the current derived slot (with checksum/timestamp updates in metadata) or use versioned filenames when retaining history matters.

### Lifecycle Tracking
Track in **both DB and workspace metadata**:
- `created`, `ingested`, `processing`, `review`, `published`, `archived`, `failed`

**DB row is source of truth for orchestration/status queries.**  
`metadata.json` mirrors status for portability and offline inspection.

Do **not** rely on filesystem marker files as the primary status mechanism.

### Fit With Current Pipeline
Start as a **thin overlay**, not a pipeline rewrite.

**Phase 1:**
- Create workspace record/prefix during ingest.
- Persist `metadata.json` + source provenance.
- Write/export artifacts into workspace-scoped blob prefixes.
- Add artifact URIs/checksums to workspace metadata.

**Phase 2:**
- Refactor stage outputs to optionally materialize page/chunk/translation/report JSON into the workspace.
- Keep PostgreSQL tables as operational truth; workspace becomes the per-book artifact package.

### Required Refactors / Gaps
1. `books` currently lacks a clean, explicit metadata/source-provenance model.
2. Output naming is currently title-based and root-script outputs are repo-root files.
3. `pipeline_jobs` is HTTP-job tracking, not a book workspace model.

### Storage Recommendation: Azure Blob / ADLS Gen2
**Reject:** GitHub repo as primary artifact archive — binary bloat, Git history growth, 50MB soft/100MB hard limits, poor streaming patterns.

**Recommend:** Azure Blob Storage / ADLS Gen2 as canonical artifact store — cheap, durable, hierarchical namespace, supports lifecycle tiers.

**Hybrid approach:** Repo stores code + small metadata/report artifacts when useful for review; blob stores heavy binaries; repo/index points at blob URLs.

### Public Archive Delivery
Separate **storage** from **delivery**:
1. **Blob Storage as origin** for binaries
2. **Static catalog site** as discovery layer (GitHub Pages if simple, small app if richer search/filtering needed)
3. Optional secondary distribution via **Hugging Face** if the goal is discoverable public datasets

If public showcase is desired: metadata index in Git/GitHub Pages, downloadable assets in Blob.

### Migration Path
Adopt with **lazy migration plus one backfill script**:
- Build a script that creates workspace metadata/prefixes for existing `books` rows and known blob artifacts.
- For in-flight books, lazily create/migrate workspace on next pipeline access if missing.
- For repo-root demo artifacts, import only the assets worth preserving.

### Risks / Trade-offs
- **Copyright:** Don't assume source PDFs are redistributable. Public-domain and licensed books are fine; others may require keeping source privately.
- **PII / sensitive text:** OCR/translation artifacts may contain annotations, stamps, or inserted personal data from scans.
- **Audio scale:** Chapter-level audio will dominate storage quickly; Blob lifecycle policies matter.
- **Future reader analytics:** If end-user analytics are added later, that's a separate privacy/GDPR concern.

### Concrete Next Moves
1. **PRODUCT FRAMING (Niobe):** Problem statement, audience, success metrics, MVP boundary for this capability.
2. After product frame is approved:
   - Add a `book_workspaces` table plus explicit `books.metadata`/provenance support.
   - Define `metadata.json` schema and artifact manifest contract.
   - Change ingest/export paths to workspace-scoped blob prefixes.
   - Add a migration/backfill script for current books and selected repo-root artifacts.
   - Keep public archive delivery separate from storage: static index + blob-backed downloads.

**Architecture Review:** See `.squad/agents/morpheus/history.md` for learnings on current artifact fragmentation.

---

## 2026-05-20: Product Framing — Workspace Abstraction + Archive + Audiobook Capability

**Author:** Niobe (Product Manager)  
**For:** Manish (Owner)  
**Date:** 2026-05-20  
**Status:** OPEN — awaiting Manish decision

### Summary
Niobe frames the product question underlying the workspace abstraction (Morpheus decision above). The architecture is sound, but three possible shapes exist:

- **Shape A:** Personal workbench (private, lineage-tracked)
- **Shape B:** Curated public heritage archive (free downloads, no audiobooks in MVP)
- **Shape C:** Publishing platform (with human review workflow and audio distribution)

All three shapes share the same storage layer. Morpheus can build shape-agnostic workspace infrastructure while Manish decides which shape Transpose becomes.

### 6 Open Questions for Manish
1. Who is the end reader (personal / public archive / publishing)?
2. What does "archive" mean (backup lineage / showcase / production distribution)?
3. Audiobook endpoint (personal listening / public distribution / embedded reader)?
4. Who reviews (just Manish / expert reviewers / community)?
5. Copyright/licensing posture across books?
6. Timeline: specific next book or forcing function?

### Recommended Path
**Build workspace storage layer now** (Morpheus's design) even though shape is undecided. The workspace is shape-agnostic. Defer: archive site design, audio pipeline, review workflow design, public metadata strategy.

**Gate:** Manish answers 6 questions or picks a shape (A/B/C) by 2026-05-22. Then Morpheus builds storage; Niobe scopes surface layer.

**Full Brief:** `.squad/decisions/inbox/niobe-workspace-product-framing.md`

---

## 2026-05-20: Workspace + Archive Product Framing (FINAL)

**By:** Niobe (PM)  
**Requested by:** Manish  
**Status:** DECISION LOCKED — ready for Morpheus architecture handoff

---

### Decision

Build **Shape A (Personal + Private Share)** immediately. Architecture must keep **Shape B (Curated Public Heritage Archive)** reachable per-book via `license.status` gate.

---

### Scope Locked

**Audience now:** Manish + close colleagues/friends via shared URL

**Audience long-term:** Global public archive of rare untranslated heritage PDFs (multilingual, multi-traditions)

**Build now:** Shape-agnostic workspace storage layer (per Morpheus's BookWorkspace design from 2026-05-20)

**Required schema additions:**
- `license.status` (per book): enum `claimed-public-domain` | `verified-public-domain` | `rights-cleared` | `rights-unknown`
- `provenance.source` (per book): URL/edition/publisher of source PDF scanned

**Public promotion rule:** Only books with `license.status ∈ {verified-public-domain, rights-cleared}` are eligible for Shape B archive listing

---

### MVP (Shape A)

**What it is:** Personal translation workbench + private URL share mechanism. Manish translates heritage texts, artifacts live in workspace storage, metadata + outputs are downloadable via private share link.

**What's in:**
- Workspace abstraction per Morpheus (book-workspaces/ hierarchy, metadata.json, input/ocr/translation/output/reports folders)
- License/provenance fields in metadata
- Private artifact download links (URL-authenticated blob storage, no auth database needed yet)
- Private status dashboard (Manish only) showing pipeline progress + license status per book
- Shared URL mechanism (signed blob URLs or simple static HTML listing, TBD by UX)

**What's explicitly out:**
- Public archive site or search interface
- Audiobook generation
- Multi-user account system or formal review workflow
- Public metadata index
- Multi-channel distribution

**Success metric:** "Manish can translate a book, share the translated PDF/ePub + glossary via a friend-shareable private URL, and retain full artifact lineage for future re-export"

---

### Shape B (Future Gate)

**When it unlocks:** When Manish has 3–5 books with `license.status = verified-public-domain` or `rights-cleared` and decides public archive is strategically valuable.

**What it becomes:** Static or low-code archive site (GitHub Pages or app) indexing published books by title, author, language, tradition, glossary preview. Download links point to blob storage. No accounts, no DRM, no ads. Always free.

**Gating mechanism:** Product promotion (Shape A → B per-book) is a manual step: Manish audits the source PDF, updates `license.status`, and marks the book eligible for archive listing.

---

### Explicitly Deferred (Not MVP, Not Shape A Scope)

- Archive site UX / static catalog design
- Audiobook generation pipeline (chapter-level TTS or human narration)
- Formal multi-reviewer/subject-matter expert workflow
- Multi-channel distribution (Spotify, Audible, archive.org mirror, Hugging Face dataset registration)
- Per-book rights research / clearance workflow (manual for now; automated clearance research tool is future nice-to-have)
- Reader analytics or user account system
- Monetization (donations, paid downloads)

---

### Risks Accepted

**Copyright uncertainty:** Manish has not formally cleared rights for any source PDF. He asserts antiquated spiritual texts are likely public domain in spirit and intent, and his translation work is defensible. Workspace tracks his per-book judgment via `license.status`; legal verification is deferred to the per-book promotion decision later. He owns the risk and the decision.

**Modern editions:** Modern republished editions (with commentary, typesetting, illustrations) carry fresh copyright on those layers. The `provenance.source` field forces him to be explicit about which edition he scanned, and `license.status` forces a per-book decision. This is documented and auditable.

**Jurisdiction drift:** Public-domain status varies by country (India, US, UK, EU). Manish is aware; workspace metadata allows per-book future clarification.

---

### Workspace Metadata Schema Additions

Morpheus's 2026-05-20 design includes:
```json
{
  "workspace_id": "...",
  "book_id": "...",
  "title": "...",
  "author": "...",
  "source_language": "...",
  "target_language": "...",
  "created_at": "...",
  "updated_at": "...",
  "status": "...",
  
  // NEW: License & Provenance
  "license": {
    "status": "claimed-public-domain | verified-public-domain | rights-cleared | rights-unknown",
    "notes": "Optional free-text field for Manish's reasoning"
  },
  "provenance": {
    "source": "URL or full citation of source PDF edition",
    "scanned_date": "...",
    "notes": "Optional: publisher, edition, commentary author, etc."
  },
  
  // Existing:
  "source_url": "...",
  "source_hash_sha256": "...",
  "pipeline_version": "...",
  "artifact_manifest": [...]
}
```

---

### Next Handoff

1. **Morpheus:** Update 2026-05-20 workspace architecture decision to include `license` and `provenance` schema above. Confirm Phase 1 plan includes initializing these fields at ingest time.
2. **Trinity:** Begin implementation of Phase 1 (thin overlay) — workspace creation at ingest, metadata.json persistence, artifact URIs in blob-scoped prefixes, schema fields baked in from day one.
3. **Tank:** Plan blob storage prefixes / lifecycle policies; confirm signed URL authentication for private share scenario works at scale.
4. **Niobe:** Pause product framing until 3–5 books are in Shape A, then re-open Shape B decision (archive site design, distribution strategy).

---

**Approved by:** Manish (2026-05-20)  
**Scope gates:** Yes — public promotion per-book via license.status  
**Architecture dependency:** None — workspace design is shape-agnostic; license fields are additive metadata  
**Risk owner:** Manish (copyright posture on source PDFs)

---

## 2026-05-20T22:52:32-04:00: BookWorkspace schema extension — license + provenance

**Author:** Morpheus (Architecture)  
**Date:** 2026-05-20T22:52:32-04:00  
**Status:** DECIDED  
**Extends:** `2026-05-20: Book Workspace Abstraction + Storage Strategy` (decisions.md)  
**Context:** Niobe's product framing closed. Scope is Shape A (private workbench for Manish + trusted contacts) now, with per-book promotion path to Shape B (curated public archive) later. Copyright posture is Manish's own judgment call — structured, not gatekept.

---

### Two New Mandatory Fields in `metadata.json`

#### 1. `license` object

```jsonc
"license": {
  "status": "<enum — see below>",
  "notes": "<optional free text>"
}
```

##### `license.status` — enum

| Value | Meaning |
|---|---|
| `rights-unknown` | Manish hasn't decided or researched. **Default at workspace creation.** |
| `claimed-public-domain` | Manish's judgment: text is old/spiritual/meant-to-spread. Not legally verified. |
| `verified-public-domain` | Manish researched it: source text predates 1900, original-language scan, no modern editorial layer adding copyright. |
| `rights-cleared` | Explicit license or permission from the rights holder. |

**Default at workspace creation:** `rights-unknown` — forces a deliberate, conscious upgrade. Workspace creation must never silently assume public domain.

**Mutability:** Mutable. Manish can upgrade (`rights-unknown` → `claimed-public-domain` → `verified-public-domain`) or correct. Every mutation must append an entry to the workspace's lifecycle history (see Lifecycle Tracking section below).

---

#### 2. `provenance` object

```jsonc
"provenance": {
  "source": {
    "url": "<string | null — download URL of the scanned PDF>",
    "edition": "<string — publisher/edition/year, e.g. 'Geeta Press, Gorakhpur, 1987 edition'>",
    "acquired_at": "<ISO 8601 datetime>",
    "notes": "<string | null — optional free text>"
  }
}
```

**All four keys are present at workspace creation.** `url` and `notes` may be `null` if unknown at ingest time. `edition` and `acquired_at` must be set (at minimum `acquired_at` defaults to the ingest timestamp if not explicitly supplied).

**Mutability:** Mutable. Corrections and enrichments are allowed; mutations are logged.

---

### Promotion-Eligibility Rule

A book is eligible for public archive promotion if and only if:

```
license.status ∈ { "verified-public-domain", "rights-cleared" }
```

Books with `rights-unknown` or `claimed-public-domain` are **workspace-private only**. They must not appear in any public catalog index, public blob URL, or shareable archive page. The promotion gate is enforced:
1. **At the storage layer** — workspace blob container/prefix ACL stays private unless `license.status` passes the rule.
2. **At the catalog layer** — the static archive index must filter on this predicate before emitting any entry.
3. **In the pipeline** — the export/publish stage must check this and refuse to promote otherwise.

This is a computed read — no separate `is_public` flag. Single source of truth: `license.status`. No denormalization.

---

### `metadata.json` — Concrete Examples

#### Shape A only (private, judgment-only)

```json
{
  "workspace_id": "ws-a1b2c3d4",
  "book_id": "beacab8b-ea5c-49e5-a60f-1ebc753c7061",
  "slug": "osho-vigyan-bhairav-tantra-vol1",
  "title": "Vigyan Bhairav Tantra Vol. 1",
  "author": "Osho",
  "source_language": "hi",
  "target_language": "en",
  "status": "review",
  "pipeline_version": "1.3.0",
  "created_at": "2026-05-20T22:52:32-04:00",
  "updated_at": "2026-05-20T22:52:32-04:00",
  "published_at": null,
  "license": {
    "status": "claimed-public-domain",
    "notes": "Osho's discourses are widely redistributed. Not formally verified. Personal judgment only."
  },
  "provenance": {
    "source": {
      "url": "https://archive.org/details/osho-vbt-vol1-hindi",
      "edition": "Diamond Pocket Books, New Delhi, 2005 edition",
      "acquired_at": "2026-04-01T10:00:00Z",
      "notes": null
    }
  },
  "artifact_manifest": []
}
```

**Promotion-eligible:** ❌ `claimed-public-domain` does not qualify. Workspace is private only.

---

#### Shape B eligible (verified, promotable)

```json
{
  "workspace_id": "ws-f9e8d7c6",
  "book_id": "c3d4e5f6-0000-1111-2222-333344445555",
  "slug": "guru-granth-sahib-punjabi-1604",
  "title": "Guru Granth Sahib",
  "author": "Multiple authors (Sikh Gurus, 16th–17th c.)",
  "source_language": "pa",
  "target_language": "en",
  "status": "published",
  "pipeline_version": "1.3.0",
  "created_at": "2026-05-18T09:00:00-04:00",
  "updated_at": "2026-05-20T22:52:32-04:00",
  "published_at": "2026-05-20T22:52:32-04:00",
  "license": {
    "status": "verified-public-domain",
    "notes": "Original text compiled 1604 CE. This scan is from a 1912 printed edition (pre-1925 US PD threshold). No modern editorial additions to the scanned pages. Verified by Manish 2026-05-18."
  },
  "provenance": {
    "source": {
      "url": "https://archive.org/details/guru-granth-sahib-1912-scan",
      "edition": "Wazir Hind Press, Amritsar, 1912 edition",
      "acquired_at": "2026-05-18T09:00:00Z",
      "notes": "Scanned by Internet Archive. 847 pages. No watermark, no modern foreword."
    }
  },
  "artifact_manifest": [
    {
      "path": "output/translated.epub",
      "checksum_sha256": "abc123...",
      "size_bytes": 512000,
      "media_type": "application/epub+zip"
    }
  ]
}
```

**Promotion-eligible:** ✅ `verified-public-domain` qualifies for Shape B public archive.

---

### DB Migration Implications

#### The `books.metadata` Bug (from history)

Prior architecture note (2026-05-20 history): `books` currently has no clean per-book metadata or source-provenance model — only `title`, `author`, `source_language`, `source_hash`, `source_blob_uri`, `status`, `page_count`. **There is no `metadata` JSONB column on `books` today.** The history note says "books.metadata JSONB is the DB-side mirror" — that column does not yet exist and must be created as part of this migration.

#### Migration Must Do Two Things

1. **Add `books.metadata` JSONB column** (the column itself is missing; this was called out as a gap but never landed a migration).

2. **Seed `license` and `provenance.source` keys** into that JSONB for all existing rows at migration time:
   - `license.status` → `"rights-unknown"` for all existing books (safe default; Manish must review each).
   - `provenance.source.url` → backfill from `books.source_blob_uri` where it looks like a download URL; `null` otherwise.
   - `provenance.source.edition` → `null` (must be filled manually per book).
   - `provenance.source.acquired_at` → `books.created_at` as a proxy.
   - `provenance.source.notes` → `null`.

#### Recommended DB Schema Shape

Option A — JSONB only (minimal migration surface):
```sql
ALTER TABLE books ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}';
-- then backfill license + provenance keys via UPDATE
```

Option B — dedicated columns (more queryable, more migration surface):
```sql
ALTER TABLE books ADD COLUMN license_status TEXT NOT NULL DEFAULT 'rights-unknown'
  CHECK (license_status IN ('rights-unknown','claimed-public-domain','verified-public-domain','rights-cleared'));
ALTER TABLE books ADD COLUMN provenance_source JSONB;
ALTER TABLE books ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}';
```

**Recommendation: Option B.** `license_status` as a real column enables indexed queries and simple WHERE clauses for the promotion gate. `provenance_source` as JSONB keeps the structured-but-flexible source object without over-normalizing. `metadata` JSONB holds everything else from the workspace contract.

#### Promotion Query (DB-side)

```sql
SELECT * FROM books
WHERE license_status IN ('verified-public-domain', 'rights-cleared')
  AND status = 'published';
```

#### Check Constraint (DB enforcement)

```sql
ALTER TABLE books ADD CONSTRAINT chk_license_status
  CHECK (license_status IN ('rights-unknown','claimed-public-domain','verified-public-domain','rights-cleared'));
```

---

### Lifecycle History — Mutation Logging

Every change to `license.status` or `provenance.source` must be appended to the workspace lifecycle log. Add a `license_history` array to `metadata.json`:

```jsonc
"license_history": [
  {
    "timestamp": "2026-05-20T22:52:32-04:00",
    "field": "license.status",
    "from": "rights-unknown",
    "to": "claimed-public-domain",
    "actor": "manish",
    "note": "Personal judgment — Osho discourses are freely redistributed."
  }
]
```

On the DB side, a `book_events` table (or existing `pipeline_state` if repurposed) should record the same transitions. Tank to decide the exact table shape.

---

### Implementation Handoff

#### Trinity (Pipeline)
- Workspace creation path: set `license.status = "rights-unknown"` and populate `provenance.source` from ingest params (URL, edition if CLI-supplied, `acquired_at = now()`).
- Export/publish stage: check `license.status` before emitting any public-facing artifact. Fail hard (not warn) if status is not in `{verified-public-domain, rights-cleared}`.
- Add `license_history` append helper to the workspace write utilities.

#### Tank (Storage / Migration)
- Write and run the DB migration: add `metadata JSONB`, `license_status TEXT` (with check constraint), `provenance_source JSONB` to `books`.
- Write the backfill script for existing rows (`rights-unknown` default, proxy timestamps).
- Ensure blob ACL policy enforces workspace-private for non-eligible books.
- Align `book_workspaces` table design (from the prior decision) with the new fields.

#### Dozer (Tests)
- Unit test: workspace creation always produces `license.status = "rights-unknown"`.
- Unit test: `provenance.source.acquired_at` is always set (never null) after creation.
- Unit test: promotion gate returns false for `rights-unknown` and `claimed-public-domain`; true for `verified-public-domain` and `rights-cleared`.
- Integration test: export/publish stage raises error (not warning) when license_status is ineligible.
- Regression test: mutation to `license.status` appends entry to `license_history` and does not silently overwrite it.
- DB constraint test: inserting a row with an invalid `license_status` value is rejected.

---

### Open Architecture Questions (Flagging to Niobe / Manish)

1. **`claimed-public-domain` visibility:** Should books with this status be shareable via private URL (invite-only, not public index) — i.e., is the Shape A "close friends" share intended to include `claimed-public-domain` books? Or only `verified-public-domain`? The current rule makes them fully private; that may be too strict for the "share with Manish's close friends" use case. Niobe to clarify.

2. **`verified-public-domain` criteria:** The enum value implies Manish has done research. Should there be a structured sub-field for the evidence (e.g., publication year, jurisdiction, rationale) rather than relying on `license.notes` free text? Useful if more books accumulate and the criteria need to be auditable. Low cost to add now, annoying to retrofit later.

3. **`rights-cleared` workflow:** If a rights holder grants permission, what artifact captures that? A signed agreement in `input/`? A URL? This is deferred per scope decision, but worth calling out the storage slot before Tank designs the workspace layout.

4. **Multi-scan editions:** What if the same text exists in two editions — one `verified-public-domain` scan and one `claimed-public-domain` scan? Are these separate workspaces, or is provenance an array? Current design assumes one workspace = one source artifact. Confirm this assumption holds.


---

## 2026-05-20: Storage location — repo vs blob clarification (addendum)

**Author:** Morpheus  
**Requested by:** Manish  
**Date:** 2026-05-20T22:57:22-04:00  
**Type:** Architecture / Storage Policy  
**Status:** DECIDED

### Decision
**(b) Hybrid Storage — Blob from day one for PDFs/audio, Git-only for small text artifacts**

- **YES for non-PDF/non-audio artifacts:** `metadata.json`, `glossary.json`, pipeline reports stay in repo
- **NO for PDFs and audio:** All heavy binaries route to Azure Blob from day one

### Rationale

**Public repo + rights-unknown = unacceptable.** A public GitHub repo is world-readable, Google-indexed, and Wayback Machine-archived within hours. Committing a `rights-unknown` PDF there is effectively publication without license — once pushed, control is lost. If rights holder surfaces, "I put it in a private repo first" is not a legal defence.

**Private repo is false solution for large PDFs.** GitHub's 100 MB hard file limit + LFS quotas will exhaust within weeks. High-res source scans (300+ MB) are impossible. LFS on free tier: 1 GB total, 1 GB/month bandwidth — one high-res book exhausts it. Binary cleanup (git filter-repo/BFG) rewrites every SHA, invalidates clones, and cannot guarantee GitHub's cache purge.

**Repo-as-transient-store is false economy.** "We'll migrate later" never works. Git history is permanent. Rights-unknown PDFs in history cannot be scrubbed without force-push and cannot guarantee removal from GitHub servers or local copies.

**Blob from day one is one-hour setup.** Azure Blob with private container + SAS-token-per-book URLs: setup in one hour. Shareable URLs work same day. Shape A (close friends) satisfied without repo involvement.

**Hybrid is clean and honest.** Small text files (metadata, glossary, reports) belong in repo — reviewable, versionable, zero copyright risk. Heavy binaries (source PDFs, audio, OCR raw) belong in Blob. Matches existing architecture; makes `license.status` gate meaningful.

### Schema Impact

- `WorkspaceArtifact.storage_backend` = typed enum: `git | blob` (constraint, not convention)
- Small metadata files → `git`; heavy binaries always → `blob`
- `metadata.json` gains `share_url` field: SAS token URL (Shape A, private) or public Blob URL (Shape B, after `license.status = verified-public-domain`)
- Public promotion gate: pure predicate — `IF license.status == 'verified-public-domain' THEN move artifact + update share_url`
- Shape A: SAS URL generated on demand, stored in `metadata.json`, rotatable without Git history

### Minimum-Viable Share-URL Path (Shape A)

1. **Azure Storage account:** `az storage account create --name transposebooks --resource-group transpose-rg --sku Standard_LRS --allow-blob-public-access false` (one account, one container per environment)
2. **Container ACL = private.** No anonymous access; all via SAS tokens (correct default for `rights-unknown`)
3. **Upload source PDF:** `az storage blob upload` → `book-workspaces/{slug}--{book_id}/input/source.pdf`
4. **Generate SAS token URL** scoped to workspace prefix, 30-day expiry: `az storage blob generate-sas ... --full-uri` → produces shareable URL
5. **Store SAS URL in `metadata.json`** under `share.source_url`. Rotation = CLI command + JSON field update (no Git history)
6. **Optional:** Point workspace URL to translated PDF (`output/translated.pdf`) instead — friends get output, lower redistribution risk

**Total setup:** under 1 hour with active Azure subscription. Only dependency: `az login`.

### Open Questions Back to Manish

1. **Active Azure subscription?** If yes, step 1 is 5 minutes. If no, that's first blocker.
2. **Share URL scope — source PDF, translated PDF, or both?** Affects blob path + whether translated artifact must pre-exist.
3. **PDF ownership: your own scans or third-party collected?** Changes whether `rights-unknown` is soft risk (pending clearance) or hard risk (no chain of custody). Architecture recommendation (Blob private + SAS) unchanged either way, but urgency of resolving `license.status` changes.

**Related Decisions:** 2026-05-20 Workspace abstraction (blob architecture), 2026-05-19 License status gate  
**Handoff:** Trinity (export/publish gate), Tank (blob ACL + workspace layout), Dozer (license gate tests)

# Niobe: Open Questions Closed — Shape A Product Rules Finalized

**Date:** 2026-05-20T23:10:06.050-04:00  
**Requested by:** Manish  
**Author:** Niobe (Product Manager)  
**Type:** Product Decision — Scope, Licensing, Share UX  
**Status:** DECIDED / CLOSED

---

## Summary

Four open questions have been answered by Manish. This note captures his answers verbatim, synthesizes the resulting firm product rules, makes a call on the WhatsApp preview feature (deferred post-MVP), and documents team-side impacts.

---

## Manish's Answers (Verbatim)

### Q1: `claimed-public-domain` visibility under Shape A

**Manish's answer:**
> "Keep them fully private until I have upgraded them to verified-public-domain."

**Translation:** Books marked `claimed-public-domain` must NOT be shareable via private URL, even to close friends. The private-until-verified rule is firm. Shape A "close friend" share capability applies only to `verified-public-domain` and `rights-cleared` books.

---

### Q2: Azure subscription

**Manish's answer:** Active subscription already logged in.

**Routing:** Morpheus owns technical setup (Blob ACL, SAS token generation, container layout). No product action required.

---

### Q3: Share URL scope + Bonus: WhatsApp preview

**Manish's answer:**
> "Both source PDF AND translated PDF. Bonus ask: When I share the URL via WhatsApp, can it also pull in a small 1-sentence title of the translated book and/or author?"

**Interpretation:** 
- **Scope:** Share URLs point to *both* source and translated PDFs (not one or the other).
- **Bonus:** WhatsApp link previews should render a small text snippet (title/author) instead of a raw Blob URL. This requires OpenGraph `<meta>` tags or a lightweight preview wrapper, not raw SAS URLs.

---

### Q4: PDF ownership

**Manish's answer:**
> "Third-party PDFs collected from the internet."

**Implication:** No chain of custody. Every book starts as `rights-unknown`. This is the *hard risk* path, not the soft path. Urgency of per-book license research is maximized.

---

## Firm Product Rules (Resulting from Answers)

### Rule 1: Private-Until-Verified (Closed Loop)

**Books must NOT be shareable via private URL if `license.status` is `claimed-public-domain` or `rights-unknown`.**

- `claimed-public-domain` → Workspace private only. Manish's judgment, not verified. Shape A close-friend share is unavailable.
- `rights-unknown` → Workspace private only. Default at workspace creation. No shared access.
- `verified-public-domain` or `rights-cleared` → Eligible for Shape A private URL share (SAS token).

**Rationale:** Manish's explicit rule closes the gap between workspace-metadata judgment and sharing policy. No exception for trusted friends; the rigor is per-book, not per-person.

---

### Rule 2: `rights-unknown` as Mandatory Default

**Every workspace created for a new book starts with `license.status = 'rights-unknown'`.**

- Not a soft default; a hard constraint enforced at workspace creation (Trinity: must set this field explicitly).
- DB column has CHECK constraint + default value (Tank: `license_status TEXT NOT NULL DEFAULT 'rights-unknown'`).
- Upgrade from `rights-unknown` is a deliberate, auditable per-book action. No silent assumption of public domain.

**Rationale:** Third-party PDFs from the internet have no chain of custody. Default to caution. Manish must research and upgrade each book explicitly.

---

### Rule 3: Deliberate License Claim (Per-Book, Per-Action)

**Claiming public domain is not a workflow shortcut; it's a conscious, auditable decision.**

- Manish upgrades a book's `license.status` only after he has verified the source PDF's provenance and rights.
- Every status change appends to workspace lifecycle history (timestamp + from/to + notes).
- "Claim PD" is not a one-click batch operation; it's a deliberate per-book action.

**Rationale:** With third-party internet PDFs, there is no good reason to batch-upgrade. Each book needs individual research. Enforce this at the UX level.

---

## WhatsApp Preview Decision: DEFERRED (Not Shape A MVP)

**Decision:** The WhatsApp preview feature (OpenGraph metadata rendering title/author) is **deferred post-MVP**.

**Reasoning:**

1. **Shape A is personal + close friends.** Friends who receive a SAS URL link are already in a high-trust context (Manish sends the URL directly). A link preview is a nice-to-have, not a blocker for usability.

2. **OpenGraph requires infrastructure.** Raw Blob SAS URLs are static, signed objects. Rendering OpenGraph metadata requires either:
   - A lightweight web proxy/wrapper service (added latency, cost, operational surface)
   - Dynamic URL rewriting (more complex, couples storage to HTTP layer)
   - Both are out of scope for Shape A MVP.

3. **MVP ship criterion:** Friends can access and download translated PDFs via private URL. That's enough. Preview can come when Shape B (public archive) is designed, which will need a proper web UI anyway.

**Recommendation:** Build Shape A with plain SAS URLs (no preview). When Shape B design begins and a public website is laid out, both WhatsApp preview and general OpenGraph metadata become natural features of the archive UI.

**Deferred to:** Phase 2 (public archive + web UI).

---

## Team-Side Impacts

### Trinity (Pipeline / Workspace Creation)

**Change:**
- Workspace creation API must **always** set `license.status = 'rights-unknown'` for new books.
- No auto-claim, no silent assumption of PD. Explicit field population is non-negotiable.

**Test:** Unit test: workspace creation produces `license.status = 'rights-unknown'` every time.

---

### Tank (Infrastructure / Database)

**Change:**
- `books` table gains column:
  ```sql
  ALTER TABLE books ADD COLUMN license_status TEXT 
    NOT NULL DEFAULT 'rights-unknown'
    CHECK (license_status IN ('rights-unknown','claimed-public-domain','verified-public-domain','rights-cleared'));
  ```
- Backfill: all existing books → `license_status = 'rights-unknown'` with migration timestamp.
- Private container ACL for Blob (already decided; no change).

**Artifact:** Tank provides schema migration + test fixtures.

---

### Dozer (Tests)

**Change:**
- Add test: workspace creation always defaults to `rights-unknown`.
- Add test: `claimed-public-domain` books are NOT eligible for shape-A-share (promotion gate rejects them).
- Extend share-URL gate tests: only `verified-public-domain` and `rights-cleared` qualify for SAS token generation.

**Artifact:** Dozer updates test suite; updates gates in Trinity's promotion logic if not already done.

---

## Newly Opened Questions

None. All four outstanding questions are now answered. License status rules are firm; rules are complete; team impacts are clear.

---

## Next Steps

1. **Morpheus:** Confirm Blob setup (SAS token generation, container ACL, workspace path layout) with Tank.
2. **Trinity + Tank + Dozer:** Begin Phase 1 schema migrations + tests using `rights-unknown` default.
3. **Niobe:** Pause product framing until 3–5 books are live in Shape A. Then re-open Shape B (public archive site design, per-book promotion workflow, researcher/scholar distribution strategy) — likely 3–4 weeks out.

---

## Related Decisions

- 2026-05-20: License status gate (copyright posture per book)
- 2026-05-20: Workspace abstraction (Blob storage, Shape A MVP scope)
- 2026-05-20: Storage location (Blob from day one, not public GitHub)
# Architecture Addendum: Share URL + WhatsApp Preview Resolution

**Author:** Morpheus (Lead / Architect)
**Requested by:** Manish
**Date:** 2026-05-20T23:10:06.050-04:00
**Status:** DECIDED — ready for Tank, Trinity, Dozer implementation
**Resolves:** Four open questions posed in 2026-05-20T22:52 license/provenance decision and 2026-05-20T22:57 hybrid-storage decision

---

## A. Azure Storage Setup — Copy-Pasteable Command Sequence

Assumes: `az login` is complete in the active terminal.

```bash
# Step 1: Confirm active subscription
az account show --query "{name:name, subscriptionId:id, state:state}" -o table

# Step 2: Create resource group (idempotent — safe to re-run if it exists)
az group create \
  --name transpose-rg \
  --location eastus \
  --output table

# Step 3: Create storage account
# NOTE: Name must be globally unique, 3–24 chars, lowercase alphanumeric only.
# If "transposebooks" is taken, try "transposebksmr" (append your initials).
az storage account create \
  --name transposebooks \
  --resource-group transpose-rg \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2 \
  --allow-blob-public-access false \
  --min-tls-version TLS1_2 \
  --output table

# Step 4: Create private container for book workspaces
az storage container create \
  --name book-workspaces \
  --account-name transposebooks \
  --auth-mode login \
  --public-access off \
  --output table

# Step 5: Enable Static Website feature (used for OG landing pages — see Section C)
az storage blob service-properties update \
  --account-name transposebooks \
  --static-website \
  --index-document index.html \
  --auth-mode login

# After this command, note the static website URL in the output under "w" (web endpoint).
# It will look like: https://transposebooks.z6.web.core.windows.net/
# Save it — this becomes the base URL for all landing pages.

# Step 6: Assign Storage Blob Data Contributor to your identity
# (Required for auth-mode login to work for reads/writes/SAS generation)
ACCOUNT_ID=$(az storage account show \
  --name transposebooks \
  --resource-group transpose-rg \
  --query id -o tsv)

USER_ID=$(az ad signed-in-user show --query id -o tsv)

az role assignment create \
  --role "Storage Blob Data Contributor" \
  --assignee "$USER_ID" \
  --scope "$ACCOUNT_ID" \
  --output table

# Step 7: Verify — list containers (expect "book-workspaces" with privateAccess)
az storage container list \
  --account-name transposebooks \
  --auth-mode login \
  -o table

# Step 8: Verify static website endpoint responds
STATIC_URL=$(az storage account show \
  --name transposebooks \
  --resource-group transpose-rg \
  --query "primaryEndpoints.web" -o tsv)
echo "Landing page base URL: $STATIC_URL"
curl -s -o /dev/null -w "HTTP %{http_code}\n" "${STATIC_URL}"
# Expect HTTP 404 (no index.html yet) — that's correct. 404 != unreachable.
```

**Estimated time:** 5–10 minutes end-to-end.
**Cost:** Standard_LRS in East US ≈ $0.018/GB/month. For Shape A book volume (tens of books, each ≤ 500 MB), < $1/month total.

---

## B. Share URL Design

### Blob Path Layout

All artifacts live under the `book-workspaces` private container:

```
book-workspaces/
  {slug}--{book_id}/
    input/
      source.pdf                ← original scanned PDF uploaded at ingest
    output/
      translated.pdf            ← generated at pipeline translation-complete stage
    landing/
      index.html                ← local workspace copy of landing page (reference)
    metadata.json               ← git-tracked (workspace canonical copy)
    glossary.json               ← git-tracked
    reports/
      pipeline-report.json
```

Static website container (`$web`, managed by Azure):

```
$web/
  {slug}--{book_id}/
    index.html                  ← served as the landing page (see Section C)
```

**Slug format:** kebab-case title, first 40 chars, ASCII-normalized. Example: `vigyan-bhairav-tantra--b7f3a2`.
**`book_id`:** UUID, last 6 hex chars used in folder name for brevity with collision-safety.

### SAS Token Policy

| Dimension       | Decision                                                    |
|-----------------|-------------------------------------------------------------|
| Scope           | **Per-file** (not per-prefix). Each PDF gets its own token. |
| Permissions     | `r` (read only). No write, delete, list.                    |
| Default expiry  | **30 days** from generation.                                |
| Storage         | `metadata.json` → `share.source_pdf_sas_url` and `share.translated_pdf_sas_url` |
| Rotation        | Manual CLI re-generation + metadata.json update + landing page re-upload. See Open Question. |

Per-file SAS is the correct scope: friends receive access to the specific PDFs they need, not to the workspace directory listing or any other workspace artifact.

**Both** source PDF and translated PDF get SAS URLs, as Manish requested. The source URL enables anyone to verify the original scan; the translated URL is the primary share artifact.

**Generation command (example — Trinity will automate this):**

```bash
# Translated PDF SAS — 30-day read-only
END_DATE=$(date -u -d "+30 days" '+%Y-%m-%dT%H:%MZ')
az storage blob generate-sas \
  --account-name transposebooks \
  --container-name book-workspaces \
  --name "{slug}--{book_id}/output/translated.pdf" \
  --permissions r \
  --expiry "$END_DATE" \
  --auth-mode login \
  --as-user \
  --full-uri \
  --output tsv
```

---

## C. WhatsApp Preview Decision: Option A — Static HTML Landing Page

**Decision: Option A. Landing page per book, served from Azure Static Website.**

### Why Not B or C

**Option B (serverless redirect function):** Heavier infra — Azure Functions, cold-start latency, deployment pipeline, costs. Overkill for Shape A friend-share. The OG-bot detection + 302-redirect pattern is clever but adds a moving part that breaks if the function cold-starts mid-scrape. Reject for now.

**Option C (defer):** Manish explicitly wants WhatsApp previews. Deferral is not an option. Reject.

**Option A wins** for three reasons:
1. **Zero new infra.** Static Website is a feature toggle on the storage account already being created (Step 5 above). No additional Azure resources.
2. **Shape A → Shape B stepping stone.** The exact same HTML page format, hosted at the exact same URL path, becomes the public Shape B archive page once `license.status` flips to `verified-public-domain`. The URL never changes for the reader. PDF links just swap from SAS to public when the time comes.
3. **WhatsApp, iMessage, Signal, Telegram all scrape raw HTTP.** A static HTML file served from `*.web.core.windows.net` has correct `Content-Type: text/html`, is reachable by scrapers, and returns OG meta tags synchronously. No JavaScript rendering required.

### Where Landing Pages Live

**Azure Static Website on the same storage account** (`$web` container, automatically created when static website is enabled).

- URL pattern: `https://transposebooks.z{n}.web.core.windows.net/{slug}--{book_id}/`
- The `$web` container is separate from `book-workspaces`. It is **public** (read-only, no directory listing), which is required for WhatsApp scrapers to fetch the HTML without authentication.
- The HTML page itself contains only: title, author, language pair, page count, translator note, and links to SAS-protected PDFs. The page does not expose any binary content.

**Landing page privacy posture:** Public-but-unindexed.
- `robots.txt` at `$web/robots.txt`: `User-agent: *\nDisallow: /` — prevents Google/Bing indexing.
- WhatsApp/iMessage/Signal scrapers do not respect `robots.txt` (they are not indexers; they are link-preview fetchers). They will fetch and parse OG tags. This is the intended behaviour.
- The URL itself is unguessable (contains UUID hex suffix). "Security by obscurity" is acceptable for Shape A friend-share — it matches the stated audience (close colleagues/friends) and the same model used by Google Docs "anyone with the link" sharing.

**Does the landing page reveal `license.status`?**
**No.** The landing page in Shape A shows: title, author, language pair, description, and PDF download links. It does not render "license status" to readers. `license.status` is an internal operational field — it gates promotion and pipeline behaviour, not what friends see. The Shape B archive page may eventually show a "Heritage Archive" badge, but that is a future surface decision for Niobe.

### Generator Approach

Trinity adds a **`generate-landing-page`** pipeline step, triggered at `translation-complete`:

1. Read `metadata.json` from the book workspace.
2. Render `landing/index.html` using a single Jinja2 template (committed to the pipeline source, no external dependencies).
3. Upload rendered HTML to:
   - `book-workspaces/{slug}--{book_id}/landing/index.html` (workspace copy, private)
   - `$web/{slug}--{book_id}/index.html` (served copy, public)
4. Set blob content-type: `text/html; charset=utf-8`.
5. Regenerate SAS URLs for `source.pdf` and `translated.pdf`.
6. Write SAS URLs and `landing_page_url` back to `metadata.json`.

**Template minimum:**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta property="og:type" content="book" />
  <meta property="og:title" content="{{ title }} — {{ author }}" />
  <meta property="og:description" content="{{ translator_note | truncate(200) }}" />
  <meta property="og:url" content="{{ landing_page_url }}" />
  {% if cover_image_blob_url %}
  <meta property="og:image" content="{{ cover_image_blob_url }}" />
  {% endif %}
  <meta property="og:site_name" content="Transpose" />
  <title>{{ title }} — {{ author }}</title>
</head>
<body>
  <h1>{{ title }}</h1>
  <p>{{ author }} · {{ source_language }} → {{ target_language }} · {{ page_count }} pages</p>
  <p>{{ translator_note }}</p>
  <a href="{{ share.translated_pdf_sas_url }}">Download Translation (PDF)</a>
  <a href="{{ share.source_pdf_sas_url }}">View Original Scan (PDF)</a>
</body>
</html>
```

No CSS framework, no JavaScript, no CDN dependency. The page must render OG tags synchronously on first byte.

---

## D. `metadata.json` Schema Additions

Fields required to support the landing page. All fields nested under logical keys for clarity. Fields already in the schema are noted.

| Field | Type | Source | Mandatory Before Share |
|-------|------|--------|------------------------|
| `title` | string | manual (Manish at ingest) | ✅ yes |
| `author` | string | manual (Manish at ingest) | ✅ yes |
| `source_language` | string (e.g. `"Hindi"`) | auto (pipeline detects) | ✅ yes |
| `target_language` | string (e.g. `"English"`) | auto (pipeline constant) | ✅ yes |
| `page_count` | integer | auto (OCR stage) | ✅ yes |
| `slug` | string (kebab-case, ASCII-safe) | auto (derived from title + book_id at ingest) | ✅ yes |
| `translator_note` | string (max 500 chars) | manual (Manish, post-translation) | ⚠️ optional but strongly recommended for OG description |
| `cover_image_blob_url` | string or null | manual (Manish uploads cover scan) | ❌ optional (OG image falls back to site default or absent) |
| `landing_page_url` | string (full HTTPS URL to `$web/{slug}--{book_id}/`) | auto (generated at landing-page step) | ✅ yes (generated automatically) |
| `share.source_pdf_sas_url` | string (full SAS URL) | auto (generated at landing-page step) | ✅ yes |
| `share.translated_pdf_sas_url` | string (full SAS URL) | auto (generated at landing-page step) | ✅ yes |
| `share.sas_expiry` | ISO-8601 datetime string | auto (generated at landing-page step) | ✅ yes (drives rotation reminder) |
| `share.generated_at` | ISO-8601 datetime string | auto | ✅ yes |
| `license.status` *(existing)* | enum | manual (post-ingest upgrade only) | — (internal; not surfaced on landing page) |
| `provenance.source` *(existing)* | object | manual / ingest params | — (internal) |

**Structural example (`share` block):**
```json
{
  "title": "Vigyan Bhairav Tantra Vol. 1",
  "author": "Osho",
  "source_language": "Hindi",
  "target_language": "English",
  "page_count": 312,
  "slug": "vigyan-bhairav-tantra-vol-1",
  "translator_note": "A Tantra classic. 112 meditation techniques as described by Shiva to Devi.",
  "cover_image_blob_url": null,
  "landing_page_url": "https://transposebooks.z6.web.core.windows.net/vigyan-bhairav-tantra-vol-1--b7f3a2/",
  "share": {
    "source_pdf_sas_url": "https://transposebooks.blob.core.windows.net/book-workspaces/vigyan-bhairav-tantra-vol-1--b7f3a2/input/source.pdf?sv=...&sig=...",
    "translated_pdf_sas_url": "https://transposebooks.blob.core.windows.net/book-workspaces/vigyan-bhairav-tantra-vol-1--b7f3a2/output/translated.pdf?sv=...&sig=...",
    "sas_expiry": "2026-06-19T23:10:00Z",
    "generated_at": "2026-05-20T23:10:06Z"
  }
}
```

---

## E. Hard Constraint: `license.status = rights-unknown` at Creation

**Manish confirmed:** Source PDFs are third-party internet scans. This makes `rights-unknown` not just a conservative default — it is the only honest starting state. There is no chain of custody. No code path may set `license.status` to anything else at book creation time.

This constraint is enforced at **four layers**. All four are required. Any one layer alone is insufficient.

### 1. Database Layer (Tank owns)

```sql
-- Column must have DEFAULT and CHECK constraint.
-- DEFAULT ensures any INSERT that omits license_status gets the right value.
-- CHECK ensures no application code can bypass it with an explicit wrong value.
ALTER TABLE books
  ADD COLUMN IF NOT EXISTS license_status TEXT NOT NULL DEFAULT 'rights-unknown'
    CHECK (license_status IN ('rights-unknown', 'claimed-public-domain', 'verified-public-domain', 'rights-cleared'));
```

The DB is the last line of defence. It must refuse any INSERT or UPDATE that violates the enum regardless of what the application layer sends.

### 2. Application Layer — Pipeline Guard (Trinity owns)

The ingest function must:
1. Never accept `license_status` as an ingest parameter. It is not in the ingest API signature.
2. After INSERT, immediately re-read `books.license_status` and assert `== 'rights-unknown'`. If not, raise `AssertionError` and roll back.

```python
# Pseudocode — Trinity implements the real version
def ingest_book(title, author, source_language, source_blob_uri, ...):
    # license_status is NOT a parameter. Period.
    book_id = db.insert_book(
        title=title, author=author,
        source_language=source_language,
        source_blob_uri=source_blob_uri,
        # No license_status argument here.
    )
    row = db.fetch_book(book_id)
    assert row.license_status == 'rights-unknown', (
        f"HARD CONSTRAINT VIOLATED: book {book_id} created with license_status={row.license_status!r}. "
        "Ingest must never set license_status. DB default should have applied."
    )
    return book_id
```

### 3. `metadata.json` Guard (Trinity owns)

`metadata.json` is written at workspace creation. The writer must:
1. Always set `license.status = "rights-unknown"` when creating a new workspace.
2. Never accept a `license_status` override from pipeline config or environment.

### 4. Tests (Dozer owns)

Dozer must write and maintain all of the following — they are not optional:

| Test | Type | What it asserts |
|------|------|-----------------|
| `test_ingest_sets_rights_unknown` | Unit | `ingest_book(...)` → `book.license_status == 'rights-unknown'` |
| `test_ingest_rejects_license_param` | Unit | `ingest_book(..., license_status='claimed-public-domain')` raises `TypeError` (param doesn't exist) |
| `test_db_default_is_rights_unknown` | Integration | Raw SQL `INSERT INTO books (...) VALUES (...)` omitting `license_status` → row has `license_status = 'rights-unknown'` |
| `test_db_check_constraint` | Integration | Raw SQL `INSERT INTO books (..., license_status='made-up')` raises `IntegrityError` |
| `test_metadata_json_default` | Unit | Workspace creation writes `metadata.json` with `license.status == "rights-unknown"` |

---

## F. Implementation Handoff

Work breakdown with the landing-page addition. Acceptance criteria are binding — done means all criteria pass.

---

### Tank (Infrastructure + DB)

**Task T-1: Azure Storage Setup**
- Run the command sequence from Section A in order.
- Confirm: `book-workspaces` container exists, public access = off.
- Confirm: Static Website enabled, base URL noted and recorded in `.squad/decisions.md` (Tank update).
- Confirm: `Storage Blob Data Contributor` role assigned; `az storage blob list` works with `--auth-mode login`.
- **Acceptance:** Section A Step 7 and Step 8 both succeed. Base URL reachable (HTTP 404 is passing — means endpoint is live, no content yet).

**Task T-2: DB Migration — license_status + metadata JSONB**
- Write and run migration: add `license_status TEXT NOT NULL DEFAULT 'rights-unknown' CHECK (...)` and `metadata JSONB` and `provenance_source JSONB` to `books` table (per 2026-05-20T22:52 decision schema).
- Write and run backfill: all existing rows get `license_status = 'rights-unknown'`, `metadata = '{}'::jsonb`, `provenance_source = '{}'::jsonb`.
- **Acceptance:** `SELECT license_status, count(*) FROM books GROUP BY 1` → exactly one row: `rights-unknown | N`. `\d books` shows check constraint. Dozer's DB integration tests pass (see E above).

**Task T-3: Static Website `robots.txt`**
- Upload `robots.txt` to `$web/robots.txt` with content:
  ```
  User-agent: *
  Disallow: /
  ```
- **Acceptance:** `curl https://transposebooks.z{n}.web.core.windows.net/robots.txt` returns 200 with the correct content.

---

### Trinity (Pipeline)

**Task TR-1: Enforce `rights-unknown` at Ingest**
- Remove any code path that accepts or writes `license_status` at book creation.
- Add the post-insert assertion (see Section E, layer 2).
- **Acceptance:** Dozer's `test_ingest_sets_rights_unknown` and `test_ingest_rejects_license_param` pass.

**Task TR-2: `metadata.json` Writer Update**
- Workspace creation writes `license.status = "rights-unknown"` in `metadata.json`. No override path.
- Add all new fields from Section D schema to the workspace creation writer: `slug`, `title`, `author`, `source_language`, `target_language`, `page_count`.
- **Acceptance:** Every newly created workspace has a valid `metadata.json` with all mandatory fields populated. `license.status == "rights-unknown"`.

**Task TR-3: Landing Page Generator Step**
- New pipeline stage: `generate-landing-page`, triggered at `translation-complete`.
- Input: `metadata.json` (must have all mandatory-before-share fields populated).
- Actions:
  1. Generate SAS URLs for `source.pdf` and `translated.pdf` (30-day read-only, per-file).
  2. Render `landing/index.html` from Jinja2 template (template committed to `src/transpose/templates/landing.html.j2`).
  3. Upload to `$web/{slug}--{book_id}/index.html` (content-type: `text/html; charset=utf-8`).
  4. Upload workspace copy to `book-workspaces/{slug}--{book_id}/landing/index.html`.
  5. Update `metadata.json`: write `landing_page_url`, `share.source_pdf_sas_url`, `share.translated_pdf_sas_url`, `share.sas_expiry`, `share.generated_at`.
- **Acceptance:**
  - `curl -s https://transposebooks.z{n}.web.core.windows.net/{slug}--{book_id}/` returns HTML containing `og:title` and `og:description` meta tags.
  - `og:title` contains book title and author.
  - SAS URL in the page (source) responds HTTP 200 to a GET request.
  - SAS URL in the page (translated) responds HTTP 200 to a GET request.
  - `metadata.json` has all `share.*` fields populated with non-null values.

**Task TR-4: `translator_note` Prompt**
- After translation-complete, if `metadata.json` has no `translator_note`, print a CLI prompt asking Manish to add one before generating the landing page (it's optional but affects OG description quality). Do not block the pipeline — use a default of `"{title} by {author}, translated from {source_language} to {target_language} by Transpose ({page_count} pages)."` if Manish doesn't provide one within the step.
- **Acceptance:** Landing page always has a non-empty `og:description` even without manual input.

---

### Dozer (Tests)

**Task D-1: License constraint tests**
All five tests from Section E. These must be written before T-2 and TR-1 are merged.

**Task D-2: Landing page tests**
- `test_landing_page_contains_og_title` — rendered HTML has `<meta property="og:title">` with correct content.
- `test_landing_page_contains_og_description` — has `<meta property="og:description">`.
- `test_landing_page_sas_urls_present` — HTML source and translated SAS URL links are present and non-empty.
- `test_sas_url_readable` — integration test: generated SAS URL responds HTTP 200.
- **Acceptance:** All tests pass in CI.

**Task D-3: `metadata.json` schema validation test**
- Write a schema validator (pydantic or jsonschema) for `metadata.json` covering all mandatory-before-share fields.
- Validate in a unit test against a fixture and against a freshly created workspace.
- **Acceptance:** Schema validator rejects a `metadata.json` missing `title`, `author`, or `landing_page_url`.

---

## G. Open Questions

**One remaining question for Manish:**

**SAS expiry rotation:** When a 30-day SAS URL expires, what triggers regeneration? Options:
- (a) Manual: Manish runs a CLI command (`transpose share rotate --book-id {id}`), landing page re-uploads automatically.
- (b) Scheduled: a nightly job checks `share.sas_expiry` across all workspaces and regenerates if within 7 days of expiry.

This affects Trinity's design of the share command and Tank's infra (option b needs a scheduled trigger). It does not block any other task — Trinity can implement option (a) first and option (b) can be layered on. **Recommendation: implement (a) now, (b) deferred.** If Manish agrees, no answer required and this question is closed.

---

**Related Decisions:** 2026-05-20T22:52 license+provenance, 2026-05-20T22:57 hybrid-storage
**Handoff:** Tank (T-1, T-2, T-3), Trinity (TR-1, TR-2, TR-3, TR-4), Dozer (D-1, D-2, D-3)
