### Decision: Strip Duplicate Chapter Titles from Translated Content

**Author:** Chani  
**Date:** 2026-04-20  
**Status:** Active  

LLM translations start each chunk with its chapter heading (e.g., "Chapter 2: Yoga and Meditation — Physical and Spiritual Discipline"). The assemble stage already renders a separate `<h1>` from the extracted title. A new `_strip_leading_chapter_title()` helper now removes the first line of translated text when it matches a chapter-heading pattern, preventing duplication in the output.

**Also fixed:**
- Foreword cleanup: `_clean_foreword()` strips LLM placeholder signatures like "[Translator's Name]"
- Foreword page numbering: `.foreword-page` now uses `page: frontmatter` CSS for roman numerals

**Impact:** Publishable-quality output — no visible duplications, clean foreword, consistent page numbering. No model or contract changes.

**Known limitation:** WeasyPrint's ToUnicode CMap for Noto Sans Devanagari produces garbled text extraction (copy/paste) despite correct visual rendering. This is an upstream WeasyPrint issue. Affects accessibility/search but not visual quality.
