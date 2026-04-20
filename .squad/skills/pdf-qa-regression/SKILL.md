# Skill: PDF QA Regression Testing

## When to Use
When validating translated/generated PDF output against a golden reference for production readiness.

## Pattern
1. **Extract text per-page** using PyMuPDF (`fitz`), not as a single blob. Page boundaries matter for ToC vs body separation.
2. **Skip front matter** when testing body content. Cover (p1), ToC (p2), foreword (p3-4) contain chapter references that confuse regex searches. Use `pages[4:]` for body.
3. **Multi-line title extraction**: PDF headings wrap across lines. Gather continuation lines that are short (<50 chars) and capitalized. Stop at prose (lowercase start or long lines).
4. **Compare strings, not just counts**: Gate 6 counts chapters and words but never compares title text. Always compare actual text content against golden `full_title` fields using word-overlap coverage.
5. **ToC extraction**: Get the ToC page directly (`pipeline_pages[:3]` for pages containing "Table of Contents") rather than regex-parsing the full text.
6. **Glossary boundary**: Use `rfind("Glossary")` to separate body from glossary section before checking Devanagari leakage.

## Key Thresholds
- Chapter title word coverage: ≥80% of golden `full_title`
- Chapter word count: ≥80% of golden `word_count_approx`
- Devanagari in body: <2% (after removing `(देवनागरी)` inline terms)
- Short paragraphs: ≤5 suspicious (<10 words) per document
- Single-char word ratio: ≤15% (OCR fragment indicator)

## Gotcha
PyMuPDF text extraction splits long headings at PDF line breaks. A title comparison like `expected in actual` fails on wrapped titles. Use word-set overlap instead.
