# Session Log: PDF Visual Fix (Issue #1)

**Date:** 2026-04-17T20-30  
**Participants:** Chani (Pipeline Dev), Thufir (Tester)  
**Outcome:** Issue #1 resolved — Devanagari font embedding + visual regression tests

## What Happened

- **Chani** fixed PDF export to embed Devanagari fonts using WeasyPrint @font-face + FontConfiguration. Reduced title page padding/font to prevent overflow. All export tests pass.
- **Thufir** wrote 12 visual regression tests in `tests/unit/test_export_visual.py`. Tests validate layout, font rendering, glossary, page count, edge cases. All passing.

## Impact

- PDFs now display cultural terms (dharma, karma) in original Devanagari script instead of tofu.
- Publication-ready output — title pages fit, no page overflow.
- Visual regression testing established for future PDF features.
- Ready for merge to main.

## Files Changed

- `src/transpose/pipeline/export.py` — Font embedding, title layout
- `tests/unit/test_export_visual.py` — 12 new tests

## Next Steps

- Merge to main
- Close Issue #1
