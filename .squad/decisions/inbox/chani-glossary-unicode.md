# Decision: Defense-in-Depth NFC Normalization for Indic Script

**Author:** Chani  
**Date:** 2026-04-19  
**Status:** Active  

Every pipeline stage that touches `original_script` (Devanagari/Gurmukhi) text now independently applies `unicodedata.normalize('NFC', text)` before storing or rendering. Shared helper lives in `src/transpose/utils/unicode.py`.

**Touchpoints:** translate.py (extraction), glossary.py (aggregation), export.py (ePub + PDF rendering), seed_glossary.py (seed read).

**Rationale:** NFC normalization is idempotent and near-zero cost. By normalizing at every layer boundary, we guarantee correct rendering regardless of whether upstream stages (OCR, LLM, seed data, future integrations) emit NFC or NFD. This eliminates an entire class of "text looks garbled" bugs.

**Impact:** Fixes issue #9. No model or interface changes. All 223 tests pass.
