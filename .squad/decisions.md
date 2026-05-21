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
