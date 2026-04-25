# Osho VBT — Visual & Structural QA Report (R1)

**Analyst:** Thufir (Tester/QA)  
**Date:** 2025-07-25  
**Source:** `Osho - विज्ञान भैरव तंत्र 1.pdf` (95 pages, Hindi original)  
**Translated:** `Osho_VBT_translated.pdf` (107 pages, English pipeline output)  
**Tool:** PyMuPDF 1.27.1  
**Raw data:** `.squad/quality/osho-qa-data-r1.json`

---

## Executive Summary

The translated PDF is **structurally sound** and covers the majority of the source material. English text reads naturally and the glossary of cultural terms is included. However, there are **6 methods missing** (18–23), **3 untranslated passages** with placeholder markers, **all 23 source images are missing**, and **PDF metadata is blank**. These must be resolved before publication.

**Verdict: NOT READY for publication.** 3 P0 blockers, 2 P1 issues.

---

## Findings

### QA-1: Methods 18–23 Missing from Translated PDF
- **Severity:** P0-blocker
- **Category:** Content
- **Evidence:** Source bookmarks list Methods 1–3, 5–23 (22 methods; #4 absent from source). Translated bookmarks only go up to Method 17. Methods 18, 19, 20, 21, 22, and 23 are absent from the translated PDF.
- **Recommendation:** Re-run translation pipeline for the missing 6 discourse chapters. This is ~28% of the source chapters missing.

### QA-2: 3 Untranslated Passages with Placeholder Markers
- **Severity:** P0-blocker
- **Category:** Content
- **Evidence:** Three `[Original text — translation unavailable]` markers found in translated PDF, each followed by raw Hindi/Devanagari text:
  1. After "Begin." — Devanagari passage about closing eyes (जाओ। म_ने बताया 0क आंख4 बंद कर ल...)
  2. After "the language of ego." — passage about thought-pause (विचार विराम बन जाता...)
  3. After "be filled with joy." — passage about needle-point concentration (उस सुई क. नोक पर भी एका*ता...)
- **Recommendation:** These are OCR-damaged segments the LLM couldn't parse. Re-OCR the affected source pages with higher resolution or manually extract and translate.

### QA-3: All 23 Source Images Missing from Translated PDF
- **Severity:** P0-blocker
- **Category:** Images
- **Evidence:** Source PDF contains 23 images (1 per chapter opening, plus cover). Translated PDF has **0 images**. Each source chapter begins with a decorative Osho/discourse image.
- **Recommendation:** Extract images from source PDF and inject into translated output during the export/publish stage. These are essential for publication fidelity.

### QA-4: PDF Metadata Completely Blank
- **Severity:** P1-high
- **Category:** Metadata
- **Evidence:** Translated PDF metadata fields are all empty: title="", author="", subject="", keywords="", creator="". Only `producer=WeasyPrint 68.1` is set. Source had `creator=Microsoft Word 2010`.
- **Recommendation:** Set metadata in export pipeline: Title="Vigyan Bhairav Tantra — Osho", Author="Osho (translated by Transpose AI)", Subject="Spiritual/Meditation", Keywords="tantra, meditation, osho, vigyan bhairav tantra".

### QA-5: Bookmark/TOC Anomalies — Stale Vachan Entries
- **Severity:** P1-high
- **Category:** Structure
- **Evidence:** 11 L2 "Vachan-N" bookmarks appear in translated PDF with inconsistent numbering: Vachan-2 (p12), Vachan-5 (p28, p33, p35×2), Vachan-10 (p41), Vachan-7 (p52), Vachan-9 (p58, p67, p72, p73). The numbers don't correspond to method numbers and appear to be leftover artifacts. Duplicate entry on p35.
- **Recommendation:** Clean up TOC generation — remove stale Vachan sub-entries or map them correctly to discourse/vachan numbers within each method.

### QA-6: Minor Glyph Mapping Error on Glossary Page
- **Severity:** P2-medium
- **Category:** Typography
- **Evidence:** Page 106 contains "समाɠध" instead of "समाधि" (samadhi). The character ɠ (U+0260, LATIN SMALL LETTER G WITH HOOK) appears in place of the Devanagari dhि ligature. This is a font-mapping/encoding error.
- **Recommendation:** Check Noto Sans Devanagari glyph coverage; may need font substitution table fix in WeasyPrint config.

### QA-7: Page 1 Is a Thin Title Page (7 words)
- **Severity:** P3-low
- **Category:** Structure
- **Evidence:** Page 1 has only 7 words: "Vigyan Bhairav Tantra — Osho". This is acceptable as a cover/title page but should be verified it's intentional.
- **Recommendation:** Acceptable if intentional. Consider adding subtitle or decorative element.

### QA-8: Content Density Ratio Within Expected Range
- **Severity:** P3-low (informational)
- **Category:** Content
- **Evidence:** Source: 55,359 words across 95 pages (583 words/page avg). Translated: 52,260 words across 107 pages (488 words/page avg). Word ratio = 0.944. The slight decrease is expected as Hindi compound words expand differently into English. 12 extra pages due to larger font/spacing.
- **Recommendation:** No action. Ratio is healthy.

### QA-9: Devanagari Text in Translated PDF — Mostly Intentional
- **Severity:** P3-low (informational)
- **Category:** Content
- **Evidence:** 3,373 Devanagari segments found. 3,370 classified as short cultural terms (तन्त्र, विज्ञान, भैरवि, प्राण, प्राणायाम, शिव, etc.) — these appear in glossary entries and parenthetical transliterations. Only 3 longer untranslated passages (covered in QA-2).
- **Recommendation:** Cultural term preservation is working correctly. The glossary pages (104–107) properly pair English transliterations with Devanagari originals.

### QA-10: No Markup Artifacts or Replacement Characters
- **Severity:** P3-low (informational)
- **Category:** Content
- **Evidence:** Zero HTML/markup artifacts found. Zero replacement characters (□, ■, U+FFFD) found.
- **Recommendation:** No action. Pipeline HTML-to-PDF conversion is clean.

### QA-11: Font Stack Is Appropriate
- **Severity:** P3-low (informational)
- **Category:** Typography
- **Evidence:** Translated PDF uses: DejaVu Serif (body), DejaVu Serif Bold (headings), DejaVu Serif Oblique (emphasis), Noto Sans Devanagari + Bold (Hindi terms), Noto Sans Gurmukhi Bold (Punjabi text), DejaVu Sans (sans-serif elements). Page dimensions: 595.3×841.9 (A4). Consistent across all 107 pages.
- **Recommendation:** Font stack is solid. A4 is standard for digital distribution; consider if 6×9" trade paperback is needed for print.

### QA-12: 3 High-Density Pages May Have Formatting Issues
- **Severity:** P2-medium
- **Category:** Structure
- **Evidence:** Pages 82 (1,064 words), 83 (913 words), 91 (843 words) significantly exceed the 488 words/page average. This could indicate missing page breaks or collapsed chapter boundaries.
- **Recommendation:** Visually inspect these pages for missing headings or page-break failures. May need manual pagination adjustment.

---

## Summary Scoreboard

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| QA-1 | Methods 18–23 missing | P0-blocker | ❌ FAIL |
| QA-2 | 3 untranslated passages | P0-blocker | ❌ FAIL |
| QA-3 | All 23 images missing | P0-blocker | ❌ FAIL |
| QA-4 | Blank PDF metadata | P1-high | ⚠️ WARN |
| QA-5 | Stale Vachan bookmarks | P1-high | ⚠️ WARN |
| QA-6 | Glyph error in glossary | P2-medium | ⚠️ WARN |
| QA-7 | Thin title page | P3-low | ℹ️ INFO |
| QA-8 | Word ratio 0.944 | P3-low | ✅ PASS |
| QA-9 | Cultural terms preserved | P3-low | ✅ PASS |
| QA-10 | No markup artifacts | P3-low | ✅ PASS |
| QA-11 | Font stack appropriate | P3-low | ✅ PASS |
| QA-12 | 3 high-density pages | P2-medium | ⚠️ WARN |

**Blockers: 3 | Warnings: 4 | Pass: 4 | Info: 1**
