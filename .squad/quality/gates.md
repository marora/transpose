# Quality Gates Specification

> These gates are blocking. If any gate fails, the pipeline run fails and the PR cannot merge.

**Effective:** 2025-07-18
**Owner:** Thufir (Quality Gate Owner)
**Enforcement:** CI pipeline, PR bot

---

## Gate Definitions

### Gate 1: OCR Sanity

| Property | Value |
|----------|-------|
| **Stage blocked** | Translation |
| **What it checks** | Detects garbled Unicode, encoding corruption, and low-confidence OCR output |
| **Input** | OCR stage output (extracted text blocks with confidence scores) |

**Pass criteria:**
- Zero text blocks where >20% of characters are non-Devanagari in a Hindi source document
- Zero text blocks where >20% of characters are non-Gurmukhi in a Punjabi source document
- Per-block OCR confidence score ≥ configured threshold (default: 0.70)
- Zero U+FFFD (replacement character) in any text block
- Zero runs of >5 consecutive ASCII-range characters in what should be Indic script blocks

**Fail behavior:**
- Pipeline halts before translation stage
- Validation report includes: block index, offending characters, confidence score, script distribution percentages

---

### Gate 2: Translation Completeness

| Property | Value |
|----------|-------|
| **Stage blocked** | Export |
| **What it checks** | Every source block has a corresponding translated output; no silent passthrough |
| **Input** | Translation stage output (source/target block pairs) |

**Pass criteria:**
- Every input block has a corresponding translated output block (1:1 mapping)
- Zero raw source-language text appearing verbatim in translated output (except glossary-preserved terms)
- Failed translation blocks use a standardized placeholder: `[TRANSLATION FAILED: block {id}]`
- Placeholder count is reported but does not fail the gate if ≤5% of total blocks

**Fail behavior:**
- Pipeline halts before export stage
- Validation report includes: missing block IDs, passthrough block IDs, placeholder count, total block count

---

### Gate 3: Glossary Integrity

| Property | Value |
|----------|-------|
| **Stage blocked** | Export |
| **What it checks** | No mixed scripts, garbled transliterations, or encoding issues in glossary entries |
| **Input** | Glossary stage output (term entries with original_script and transliteration fields) |

**Pass criteria:**
- All `original_script` fields pass NFC normalization check (`unicodedata.normalize('NFC', text) == text`)
- Zero U+FFFD (replacement character) in any glossary field
- Zero Latin-script characters (U+0041–U+007A, U+00C0–U+024F) in `original_script` fields
- All `transliteration` fields contain only Latin characters, spaces, and standard diacritics
- No empty `original_script` or `transliteration` fields

**Fail behavior:**
- Pipeline halts before export stage
- Validation report includes: term ID, field name, offending characters, NFC normalization diff

---

### Gate 4: Document Structure

| Property | Value |
|----------|-------|
| **Stage blocked** | Export |
| **What it checks** | Table of Contents, chapters, and foreword are coherent and structurally sound |
| **Input** | Assemble stage output (Manuscript object) |

**Pass criteria:**
- ToC entry count == chapter count (every chapter appears in ToC, no orphans)
- Foreword is present and non-empty (>100 characters)
- Chapter ordering is sequential (no gaps, no duplicates)
- Page numbering is sequential (no gaps; roman numerals for front matter, arabic for chapters)
- No empty chapters (each chapter has >0 content blocks)

**Fail behavior:**
- Pipeline halts before export stage
- Validation report includes: ToC entry count vs chapter count, empty chapter IDs, foreword length, page numbering issues

---

### Gate 5: Artifact Availability

| Property | Value |
|----------|-------|
| **Stage blocked** | Release |
| **What it checks** | Generated artifacts are uploaded, accessible, and structurally valid |
| **Input** | Export stage output (PDF and ePub file paths/URIs) |

**Pass criteria:**
- PDF file exists and is non-zero size
- ePub file exists and is non-zero size
- PDF is a valid PDF (magic bytes: `%PDF-`)
- ePub is a valid ZIP with `mimetype` entry
- Upload to artifact store succeeds (HTTP 2xx response)
- Stable download links return HTTP 200 with correct `Content-Type`
- If upload fails for either artifact → **entire pipeline run fails**

**Fail behavior:**
- Run marked as failed; no release
- Validation report includes: file paths, file sizes, upload status codes, link verification results

---

## Gate Execution Order

```
OCR Sanity ──→ Translation Completeness ──→ Glossary Integrity ──→ Document Structure ──→ Artifact Availability
   (post-OCR)      (post-translate)           (post-glossary)         (post-assemble)        (post-export)
```

Each gate runs after its corresponding pipeline stage. Gates are **sequential** — a failure at any point halts the pipeline.

---

## Validation Report Format

Every gate produces a JSON report fragment. The final validation report is a single JSON file:

```json
{
  "run_id": "uuid",
  "book_id": "uuid",
  "timestamp": "ISO-8601",
  "gates": {
    "ocr_sanity": { "status": "PASS|FAIL", "details": { ... } },
    "translation_completeness": { "status": "PASS|FAIL", "details": { ... } },
    "glossary_integrity": { "status": "PASS|FAIL", "details": { ... } },
    "document_structure": { "status": "PASS|FAIL", "details": { ... } },
    "artifact_availability": { "status": "PASS|FAIL", "details": { ... } }
  },
  "overall": "PASS|FAIL"
}
```

This format is machine-readable for CI automation and human-readable for PR review.
