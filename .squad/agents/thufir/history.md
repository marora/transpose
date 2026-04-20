# Project Context

- **Owner:** Mani
- **Project:** Transpose — agentic pipeline that translates scanned/digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence for OCR and Azure OpenAI GPT-4o for literary/cultural translation. Culturally significant words (atman, dharma, karma) must be preserved untranslated and collected into a glossary. Output: publication-ready ePub/PDF.
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights
- **Created:** 2026-04-17

## Architecture from Stilgar (2026-04-17T19:50:55Z)

7-stage sequential pipeline (Ingest → OCR → Chunk → Translate → Glossary → Assemble → Export). Test structure mirrors source: `tests/unit/` for module tests (mocking service wrappers), `tests/integration/` for end-to-end against real Azure fixtures. Unit tests validate contracts (type validation, error handling, edge cases). Integration tests ensure Azure SDK calls work correctly. All stages idempotent (re-runs skip completed work). 

**Test requirements:**
- Mock service wrappers (DocumentIntelligenceService, TranslationService, GlossaryService, StorageService) in unit tests
- Real Azure fixtures in integration tests (can reuse Managed Identity)
- Contracts defined in `docs/api-contracts.md` — validate types in unit tests
- Each stage has async `run(input: StageInput) -> StageOutput` signature — test async behavior
- Redis + PostgreSQL for integration tests (fixtures handle teardown)

**Key files:** `tests/unit/`, `tests/integration/`, `docs/api-contracts.md`, `src/transpose/models/` (domain objects)

## Core Context

### Initial Test Suite & Visual Testing (2026-04-17, 2025-01-06, 2025-07-24)

Delivered 147 total tests (10 existing + 137 new) covering all 7 pipeline stages, services, and integration. Unit tests mock service layer (AsyncMock + fakeredis). Contract-based testing validates `docs/api-contracts.md` shapes. **P0 focus: 16 parametrized cultural term preservation tests** (7 Hindi + 7 Punjabi + 2 edge cases).

Created `tests/unit/test_export_visual.py` with 12 visual regression tests using PyMuPDF to inspect PDF output quality (title layout, Devanagari rendering, glossary, page counts, edge cases).

Early critical issue tests (#6, #7, #8) covered devanagari OCR normalization (NFC, codepoint validation, U+FFFD detection), translation completeness (placeholder text, block count, partial failure), and paragraph joining (cross-page terminal punctuation, danda/double danda terminators, continuation heuristics). All tests serving as regression detectors for Chani's fixes.

### Early-Week Issue Tests (2026-04-18)

Wrote validation tests for issues #9–#13 (Devanagari normalization, cover page, ToC generation, page numbering, page inflation). Tests created before fixes to verify acceptance criteria.

## Learnings

**Files modified:**
- `tests/unit/pipeline/test_glossary.py` — Added 4 test classes (Issue #9: Unicode normalization)
- `tests/unit/pipeline/test_export.py` — Added 5 test classes (Issues #10–#13: cover page, ToC, page numbering, foreword)

| **TOTAL** | **20/20** | **—** | **20** |

**Key Findings:**
- Page count for 10-page Hindi source: 14 pages (within 1.5× threshold, ✓ PASS)
- ToC page reduction: 4 pages → 1 page (chapter title extraction working correctly)
- Devanagari rendering: 100% correct (no tofu, font embedding solid)
- Glossary: 51 terms extracted, all NFC-normalized, 0 garbled

**Gate Unit Tests Status:** All 36 gate unit tests PASS (no longer skipping or xfailing page inflation test — the bug is fixed).

**Keys for next sprint:**
- Page inflation test demonstrates regression test value — would have caught the bug on commit
- Gate unit tests validate both happy path (PASS conditions) and fail conditions (known bad inputs)
- Glossary NFC normalization at every stage boundary (translate, glossary, export) prevents future Unicode rendering bugs
- Visual regression tests (PyMuPDF) catch PDF layout issues (overflow, page breaks, Devanagari rendering)

**Confidence:** All regression test infrastructure in place. Future pipeline changes are validated against known-good baseline (golden reference data).

### Session 2026-04-20: Golden-Targeted QA Gate (Objective 2)

**Delivered:** Gate 6 (`golden_targeted_qa_gate`) + 23 new tests + 2 golden reference JSON files.

**Golden Reference Artifacts:**
- `tests/golden/golden-source-fingerprint.json` — structural fingerprint of 10-page Hindi source (9 chapters, per-chapter word counts, key terms)
- `tests/golden/golden-target.json` — stable English translation reference with per-chapter word counts, glossary requirements, quality thresholds
- Update policy: version-controlled, updated ONLY when pipeline legitimately improves

**Gate 6 Checks (5 sub-checks):**
1. Structural match — chapter count, section presence (cover/ToC/foreword/glossary), sequential ordering
2. Content completeness — per-chapter word count within ±30% of golden target
3. Script hygiene — Devanagari ratio in English body < 2% (glossary terms exempted)
4. Glossary integrity — 14 required preserved terms present, ≥35 total entries
5. No regression — page count ≤ 1.5× source (10 pages → max 15)

**Test Suite (`tests/regression/test_golden_targeted_qa.py`) — 23 tests:**
- Source fixture validation (4): PDF exists, 10 pages, fingerprint valid
- Target fixture validation (5): JSON exists, chapters/structure/glossary/thresholds valid
- Good candidate (4): real PDF passes, details populated, chapters detected, glossary found
- Bad candidate (6): missing chapters, Hindi bleed, missing glossary, missing files, excessive pages
- Tolerance boundaries (4): word count ±30%, page count 1.5×, far-below fails

**Integration:**
- Runner calls golden QA gate after artifact_availability (Gate 5)
- gate-expectations.json includes `golden_targeted_qa: PASS`
- README.md documents 3-artifact QA process

**Key Decisions:**
- fitz can't render Devanagari with default fonts → Hindi bleed test uses `pytest.skip` if font unavailable
- Chapter 9 (Conclusion) regex boundary: uses `Glossary|$` terminator
- Word count tolerance tests use per-chapter golden values (not flat counts)
- Gate uses PyMuPDF for PDF text extraction (same as existing visual tests)

**Status:** 347 passed, 1 pre-existing env failure, 4 xfailed. All ruff clean.

---

### Cross-Agent Update: Chani's PDF Quality Fixes (2026-04-20)

Chani completed **3 PDF quality fixes** that lock in the baseline for your golden-target validation:

1. **Duplicate chapter titles stripped** — `_strip_leading_chapter_title()` removes chapter headings from start of translated content (prevents "Chapter 2" appearing twice)
2. **Foreword placeholder cleanup** — `_clean_foreword()` strips "[Translator's Name]" placeholders
3. **Foreword page numbering fixed** — roman numerals (i, ii, iii) via `page: frontmatter` CSS

**All 5 gates pass.** The PDF output is now the golden baseline your QA framework validates against. Any future changes to translation/export logic will need to update `golden-target.json` intentionally.

Known WeasyPrint issue: ToUnicode CMap produces garbled text extraction for Devanagari (copy/paste), but visual rendering is perfect. Does not affect visual quality.

### Session 2026-04-20: Golden-Target QA Hardening (Issue #14)

**Delivered:** `validate_golden_target()` function in gates.py + 34 new tests across 2 files.

**Gate 6 hardening (`src/transpose/pipeline/gates.py`):**
- Added `validate_golden_target(golden: dict) -> list[str]` — validates the golden target JSON itself before using it as a reference
- Checks: U+FFFD replacement characters (garbled text), empty chapter titles, zero/missing word counts, missing cover/ToC sections, deep JSON-wide U+FFFD scan
- Gate 6 now calls validation before comparing candidate — corrupt golden target = immediate gate FAIL with details
- New constants: `_GOLDEN_TARGET_MIN_CHAPTERS = 1`, `_GOLDEN_TARGET_MIN_CHAPTER_WORDS = 5`

**New test file (`tests/regression/test_golden_target_integrity.py`) — 19 tests:**
- File-level: exists, valid JSON, no U+FFFD, no null bytes
- Chapters: count=9, sequential, non-empty titles, positive word counts, no garbled titles/phrases
- Structure: cover present, ToC present, cover required, glossary present, thresholds defined
- Glossary: required terms present, terms have names, no garbled terms, reasonable min_entries

**Strengthened Gate 6 tests (`tests/regression/test_golden_targeted_qa.py`) — 15 new tests:**
- Self-validation (8): valid golden passes, garbled title/key_phrase detected, empty title detected, zero word count, missing cover/toc, no chapters array
- Gate rejects corrupt golden (2): garbled golden target → gate FAIL, empty chapters → gate FAIL
- Structural alignment (2): reordered chapters detected, chapter count divergence detected
- Allowed exceptions (3): Foreword/Glossary/ToC don't cause false failures

**Bug fix:** Boundary tests (`test_word_count_at_lower/upper_boundary_passes`) were hardcoding golden word counts that drifted from actual `golden-target.json`. Fixed to read dynamically from the file — no more silent drift.

**Status:** 380 passed, 1 skipped (fitz Devanagari rendering), 4 xfailed, 1 pre-existing env failure. All ruff clean.

**Key insight:** The golden target was being trusted blindly as the reference standard. If it had garbled text or empty chapters, Gate 6 would pass bad candidates against a bad baseline. Now the gate validates its own reference before using it — trust nothing.


## Session 2026-04-20: Golden Target Validation Hardening (Issue #14)

**Delivered:** Implemented validate_golden_target() in gates.py to catch corruption before Gate 6 uses golden target as reference. Created 19-test integrity suite in test_golden_target_integrity.py. Updated 15 gate tests to read golden values dynamically. Committed as 2c07766. 380 total tests pass.

**Key accomplishments:**
- `validate_golden_target()` checks for U+FFFD replacement characters, empty titles, zero word counts, missing cover/ToC sections
- Gate 6 returns FAIL immediately with `golden_target_validation_errors` in details if baseline fails validation
- Standalone integrity test suite validates golden-target.json independently of gate logic
- Boundary tests now read from golden-target.json dynamically — no more hardcoded word count drift

**Cross-Agent:** Chani regenerated golden-target-english.pdf with ToC page numbers and full chapter headings. Fixed chapter heading regex in assemble.py. Updated golden-target.json with accurate word counts reflecting new chapter format.

**Status:** Issue #14 closed. All 380 tests pass. Ready for origin/master.

### Session 2026-04-21: Production Readiness QA Gap Analysis

**Delivered:** `tests/regression/test_production_readiness.py` — 61 new tests across 8 test classes covering quality dimensions that Gate 6 misses.

**Root Cause:** Manish reported chapter titles are partial. Confirmed: 5 of 9 chapters in the pipeline output PDF have truncated titles — the subtitle after the em-dash is completely missing. Gate 6 only checks chapter count via `Chapter N:` regex, never compares actual title text against `golden-target.json` `full_title` fields.

**Concrete Findings:**
- Ch1: "Dharma and Karma" → should be "Dharma and Karma — The Message of the Gita"
- Ch2: "Yoga and Meditation" → should be "— Physical and Spiritual Discipline"
- Ch3: "Sikh Tradition" → should be "— Sangat, Langar, and Seva"
- Ch5: "Hindi Literature" → should be "— From Kabir to Premchand"
- Ch9: "Conclusion" → should be "— The Continuity of Indian Culture"
- Golden reference PDF has full titles. Pipeline PDF strips subtitles.

**8 Test Classes Implemented:**
1. **ChapterTitleCompleteness** (11 tests) — Extracts body chapter headings, compares word overlap against golden `full_title`. 5 correctly FAIL.
2. **ContentCoverage** (10 tests) — Per-chapter word counts vs golden target, ≥80% threshold. All PASS.
3. **ScriptHygiene** (2 tests) — Devanagari ratio in body, sentence fragment detection. All PASS.
4. **StructuralAlignment** (7 tests) — Chapter count, ordering, cover/ToC/foreword/glossary presence. All PASS.
5. **GarbledTextDetection** (5 tests) — U+FFFD, null bytes, encoding errors, symbol sequences, OCR fragments. All PASS.
6. **TocAccuracy** (11 tests) — ToC entries match body chapters, entry count, short titles present. All PASS.
7. **GlossaryConsistency** (12 tests) — Required terms, garbled text, min entries, mixed-script, 8 parametrized term checks. All PASS.
8. **ParagraphIntegrity** (3 tests) — Short paragraph detection, long paragraph detection, chapter content non-empty. All PASS.

**What existing gates were missing:**
- Chapter title completeness (subtitles after em-dash)
- ToC-to-body title matching
- Garbled text detection in final PDF output
- Paragraph integrity checks
- OCR fragment detection in output

**Full suite result:** 436 passed, 5 intentional failures (title truncation), 1 pre-existing env failure, 1 skipped, 4 xfailed. All ruff clean.

**Decision filed:** `.squad/decisions/inbox/thufir-production-readiness-gate.md` — recommends production readiness tests as release gate (not pipeline gate), Chani to fix title truncation bug.

**Key insight:** Gate 6 validates *structure* (chapter count, word counts, ratios) but not *content fidelity* (actual title text, subtitle presence). The pipeline passes all structural gates while producing truncated titles — the tests need to compare strings, not just count things.
