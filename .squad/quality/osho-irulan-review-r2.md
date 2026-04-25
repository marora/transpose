# Irulan Publication Review — Round 2

## Verdict: ❌ FAIL

## Summary

Three of four P0 blockers from R1 remain unfixed. The Devanagari garbling is *reduced* (the new font handles some conjuncts) but 46 garbled characters still appear across 22 pages, including critical glossary entries like शक्ति, समाधि, निर्वाण, and कुण्डलिनी. The untranslated-chunk fix was not applied — raw Hindi still leaks through on 3 pages with the old `[Original text — translation unavailable]` marker. TOC deduplication is non-functional: 7 duplicate L2 entries persist (Vachan-5 ×3, Vachan-9 ×4). Additionally, the "Vachan→Pravachan" terminology rename was never applied to bookmarks or TOC. On the positive side: Gurmukhi contamination is resolved, running headers now render, the ePub has a copyright page, and metadata is correct. But we cannot publish with garbled script, leaked source text, and a broken TOC.

## R1 Finding Status

| # | R1 Finding | Status | Notes |
|---|-----------|--------|-------|
| P0-1 | Glossary garbled Devanagari (18 chars) | ❌ PARTIALLY FIXED — STILL PRESENT | Reduced but not resolved. 46 garbled chars across 22 pages. New font (647KB/1117 glyphs) improved some conjuncts but still fails on: शक्ति→`Uȫèत`, समाधि→`समाȤध`, निर्वाण→`ȡनविार्वाण`, कुण्डलिनी→`कुण्डȥलिनी`, विज्ञान→`ȡविज्ञान`, शिव→`ȥUव`, सिद्धासन→`ȥसद्धासन`, and many more. The garbling pattern (Latin-like substitution chars `ȡȤȥȫèĀȩ`) suggests missing glyph fallback, not a font-size issue. Need a font with full conjunct+matra coverage, or pre-render Devanagari as SVG/image. |
| P0-2 | 3 untranslated chunks with raw Hindi | ❌ STILL PRESENT | Pages 40, 81, 91 still show `[Original text — translation unavailable]` followed by raw Hindi/OCR artifacts. The intended replacement string `[A passage from the original text could not be translated and has been omitted.]` was never applied. Page 40 leaks ~150 chars of Hindi. Page 91 additionally contains a Malayalam character `഍` (U+0D0D) — new script contamination. |
| P0-3 | TOC duplicate Vachan entries | ❌ STILL PRESENT | 7 duplicate L2 entries remain: Vachan-5 appears 4× (pp 29, 34, 36, 36) and Vachan-9 appears 5× (pp 59, 68, 73, 74, 79). The dedup fix (keying on `(title, level)` instead of `(chapter, title, level)`) should have collapsed these — either the fix wasn't deployed or the dedup runs too late in the pipeline. |
| P0-4 | Gurmukhi script contamination ("amrit") | ✅ FIXED | "amrit" glossary entry now shows `अमृत` (Devanagari). No Gurmukhi characters (U+0A00–0A7F) found anywhere in the PDF. |
| P1 | Running headers not rendering | ✅ FIXED | "Vigyan Bhairav Tantra — Osho" appears consistently at y≈23 on sampled pages (10, 20, 30, 50, 70, 90). |
| P1 | ePub missing copyright page | ✅ FIXED | `copyright.xhtml` present in ePub spine after cover, contains proper attribution to Osho Foundation International and Transpose AI Translation Pipeline. |
| P1 | Images missing (403 blob errors) | ⚠️ KNOWN / NOT CODE | No images in PDF. This is an infrastructure/auth issue with blob storage, not a code defect. Does not block publication approval if images are decorative. |

## New Findings

### P0 Blockers

#### P0-5: Vachan→Pravachan terminology rename not applied
The R2 fix notes state "Vachan→Pravachan: Terminology fix in heading patterns" but all 13 L2 TOC bookmark entries still read "Vachan-N", not "Pravachan-N". The printed TOC on pages 2–3 also shows "Vachan-N". The body text on page 20 shows "Vachan-2" in the sub-heading. The rename was either not deployed or is scoped incorrectly.

#### P0-6: Malayalam script contamination on page 91
Page 91 contains the Malayalam character `഍` (U+0D0D) adjacent to raw Hindi text in an untranslated passage. This is a new script contamination vector (distinct from the R1 Gurmukhi issue). The OCR/source-text pipeline is leaking non-Devanagari Indic script.

#### P0-7: Method 4 missing from sequence
The chapter sequence jumps from "Tantra Sutra — Method 3" directly to "Tantra Sutra — Method 5". Method 4 is absent from both the TOC bookmarks and the printed TOC. This is either a source-text gap or a translation pipeline skip. Must be investigated — a missing chapter is a publication blocker.

### P1 High

#### P1-1: Garbled Devanagari in body text (not just glossary)
The garbling is not confined to the glossary. Body text on 17 non-glossary pages contains garbled Devanagari in parenthetical transliterations (e.g., page 5: `ȡविज्ञान`, page 11: `ȡनविार्वाण`, page 23: `समाȤधि`, page 27: `पȞरȤधि`, page 56: `बोȤधिȣचत्त`, page 66: `ब्रह्माȩस्म`). These inline terms are meant to help readers connect English to Sanskrit — garbled rendering defeats that purpose entirely.

#### P1-2: Page number / roman numeral inconsistency
Title page shows "i", copyright "ii", TOC "iii"/"iv" — but Arabic numbering starts at page 5 (Translator's Foreword). The TOC entries reference Arabic page numbers that are offset from the actual PDF page indices. This is a minor usability issue but worth fixing.

### P2 Low

#### P2-1: Metadata missing creation date
`creationDate` and `modDate` are empty strings. Should be set for archival and versioning purposes.

#### P2-2: No images — decorative or essential?
Zero images in the 108-page PDF. If any diagrams (e.g., chakra illustrations, meditation postures) were intended, they are missing. If all images were decorative, this is acceptable. Needs editorial confirmation.

## Verification Commands Used

```python
import fitz
doc = fitz.open("Osho_VBT_translated.pdf")
# 108 pages, PDF 1.7, WeasyPrint 68.1
# Metadata: title="Vigyan Bhairav Tantra Volume 1", author="Osho"
# TOC: 39 entries, 7 duplicates, 0 "Pravachan" entries
# Garbled chars: 46 across 22 pages (regex: [ȡȤȥȫèĀȩȞɏ])
# Untranslated markers: 3 (pages 40, 81, 91)
# Gurmukhi: 0 occurrences
# Malayalam: 1 occurrence (page 91)
# Images: 0
```

## Final Recommendation

**Do not publish.** Three of four original P0 blockers remain, and three new P0 issues were identified (terminology rename not applied, Malayalam contamination, missing Method 4). Specifically:

1. **Font rendering (P0-1)**: The NotoSansDevanagari.ttf upgrade helped but is insufficient. Consider: (a) using the full Noto Sans Devanagari variable font, (b) testing with Lohit Devanagari or Shobhika as fallback, or (c) pre-rendering Devanagari strings as inline SVG in the HTML before WeasyPrint processes it.

2. **Untranslated chunks (P0-2)**: The replacement logic is not executing. Verify that the chunk-replacement runs *after* translation and *before* PDF export. Add a post-export assertion that `[Original text` does not appear in extracted text.

3. **TOC dedup (P0-3)**: The `(title, level)` dedup key should work in theory. Check whether the dedup runs before or after WeasyPrint generates bookmarks — WeasyPrint may be re-generating them from headings.

4. **Vachan→Pravachan (P0-5)**: Grep the HTML template and heading-generation code for "Vachan" — the rename likely needs to happen in the source heading pattern, not just the glossary.

5. **Method 4 (P0-7)**: Check the source PDF chapters — is Method 4 present in the Hindi original? If so, the translation pipeline skipped it. If not, add an editorial note.

A Round 3 review will be required after these fixes are applied.

---
*Review conducted by Princess Irulan, Publication Editor*
*Date: Round 2 review of Osho VBT Vol. 1 English translation*
*Artifact: Osho_VBT_translated.pdf (108 pages, PDF 1.7)*
