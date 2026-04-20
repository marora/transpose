# Decision: ToC Page Numbers via target-counter() + Full Chapter Headings

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  
**Issue:** #14

## Context

Golden Target PDF and pipeline output both lacked ToC page numbers. Pipeline chapter headings were truncated at em-dash due to non-greedy regex in `_extract_chapter_title()`.

## Decision

1. **ToC page numbers** use WeasyPrint's `target-counter(attr(href url), page)` CSS function with `<a href="#chapter-N">` anchor links. This is applied in both the golden target script and the pipeline export.

2. **Chapter headings** now include the full title including em-dash subtitles (e.g., "Chapter 1: Dharma and Karma — The Message of the Gita" instead of just "Chapter 1: Dharma and Karma").

3. **Chapter anchor IDs** (`id="chapter-N"`) are added to all `<h1>` tags in both assembled HTML and golden target HTML to support ToC cross-referencing.

## Impact

- **Chani (Pipeline):** `assemble.py` and `export.py` now produce full chapter headings and page-numbered ToC.
- **Thufir (Testing):** `golden-target.json` word counts and `full_title` fields updated. All 76 regression tests pass.
- **Golden Target:** PDF regenerated with ToC page numbers. Stable artifact — do not regenerate automatically.

## Key Files

- `scripts/generate_golden_target_pdf.py` — golden target generator
- `src/transpose/pipeline/assemble.py` — `_extract_chapter_title()` fix
- `src/transpose/pipeline/export.py` — ToC `target-counter()` CSS
- `tests/golden/golden-target.json` — updated word counts and full_titles
- `tests/golden/golden-target-english.pdf` — regenerated
