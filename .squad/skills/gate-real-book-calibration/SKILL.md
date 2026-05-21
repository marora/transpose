# Skill: Gate Real-Book Calibration

**Slug:** gate-real-book-calibration  
**Owner:** Trinity  
**Created:** 2026-05-21T11:40:56-04:00

---

## Summary

Quality gate thresholds must be calibrated against real book corpora, not only against synthetic test inputs. Synthetic fixtures can confirm a gate fires on obvious bugs but cannot validate that the threshold doesn't false-positive on legitimate real-world content.

---

## Pattern

> Before shipping a quality gate with a numeric threshold (`N occurrences`, `>X%`, `count >= K`), ask:
> **"Can this exact pattern appear in a well-formed real book?"**
> If yes → the threshold is too aggressive. Adjust or narrow the scope.

---

## Known False Positive Patterns (real-book corpus findings)

### 1. Repeated images — `export_rendering` gate
- **Trigger:** `N image(s) repeated 3+ times across pages`
- **Real-book cause:** Cover art, chapter ornaments, publisher logos, front/back matter art legitimately repeat.
- **Fix (2026-05-21, Issue #90):** Require **2+ distinct large images** each repeating 3+ times. A single repeated image is never flagged.
- **Rule:** If only ONE image repeats (no matter how large or how often), it is almost certainly intentional design.

### 2. Garbled Unicode — `glossary_integrity` gate (U+FFFD)
- **Trigger:** `'shri': U+FFFD in original_script`
- **Real-book cause:** OCR may partially garble a glyph, leaving recoverable Devanagari mixed with U+FFFD. The LLM preserves the garbled form; the glossary stage must scrub before writing.
- **Fix (2026-05-21, Issue #89):** Strip U+FFFD at write time (final defensive pass). If the remainder is valid Devanagari, keep it; if Latin-only or empty, clear the field.
- **Rule:** Scrub encoding artifacts at every write site, not just at read time.

---

## Implementation Checklist

When writing or reviewing a quality gate:

1. **Test with synthetic input** — confirm the gate fires on the bug pattern.
2. **Test with a real-book fixture** — confirm the gate does NOT fire on legitimate content (cover art, ornaments, front matter, etc.).
3. **Document the threshold rationale** — why is the number N and not N-1 or N+1?
4. **Add both test cases** — a "true bug" fixture (FAIL) and a "real book shape" fixture (PASS).
5. **Re-calibrate after the first real-book run** — thresholds that seemed safe on small test PDFs often need tightening on 200-page scanned books.

---

## Related Decisions

- `.squad/decisions/inbox/trinity-export-rendering-heuristic.md`
- `.squad/decisions/inbox/trinity-glossary-ufffd-scrub.md`
