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

