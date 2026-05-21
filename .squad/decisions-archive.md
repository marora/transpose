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

