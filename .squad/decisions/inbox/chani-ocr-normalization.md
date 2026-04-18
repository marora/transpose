# Decision: Devanagari OCR Normalization and Validation

**Author:** Chani  
**Date:** 2026-04-19  
**Status:** Proposed  
**Issue:** #7 — Garbled Devanagari OCR output

## Context

OCR pipeline produced garbled Unicode for Hindi pages because Document Intelligence had no locale hint and extracted text was not normalized.

## Decision

1. **Locale hint:** Pass `locale="hi"` to `begin_analyze_document()` for all Hindi source books. The parameter is a keyword arg on the SDK method.
2. **NFC normalization:** Apply `unicodedata.normalize('NFC', text)` to ALL extracted text — both PyMuPDF digital path and Document Intelligence scanned path.
3. **Confidence threshold:** Lowered `needs_review` threshold in `ocr_client.py` from 0.7 to 0.5. Pages below 0.5 are genuinely garbled and should be flagged.
4. **Validation layer:** New `_validate_page()` in `ocr.py` checks three things: minimum text length, Devanagari codepoint presence (for Hindi), and excessive replacement characters. Runs on both extraction paths.

## Impact

- **Chani:** Both `ocr_client.py` and `pipeline/ocr.py` updated. No model changes.
- **Thufir:** All 39 existing OCR tests pass. May want to add integration tests for validation edge cases.
- **Idaho/Stilgar:** No infra or architecture changes needed.

## Rationale

NFC is the W3C-recommended normalization form and prevents composed/decomposed mismatches downstream (translation LLM, ePub rendering, glossary matching). Locale hint is the Azure-recommended approach for non-Latin scripts. Validation catches structural failures that confidence scoring alone misses.
