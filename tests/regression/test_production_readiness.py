"""Production-readiness checks for the translated PDF output.

These tests go beyond the existing Gate 6 (golden_targeted_qa) by catching
quality issues that slip through structural/numerical checks:

  1. Chapter title completeness — full titles with subtitles, not truncated
  2. Content coverage — per-chapter word counts vs golden target
  3. Script hygiene — no stray Devanagari outside glossary/preserved terms
  4. Structural alignment — chapter count, ordering, required sections
  5. Garbled text detection — U+FFFD, encoding errors, OCR fragments
  6. ToC accuracy — ToC entries match body chapter titles
  7. Glossary consistency — preserved terms present, not garbled
  8. Paragraph integrity — no broken/suspiciously short content blocks

All tests compare the pipeline output PDF against the golden-target.json
reference and/or the golden-target-english.pdf baseline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import fitz  # PyMuPDF
import pytest

pytestmark = [pytest.mark.regression]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PIPELINE_PDF = REPO_ROOT / "Test_Hindi_Book_final.pdf"
GOLDEN_PDF = REPO_ROOT / "tests" / "golden" / "golden-target-english.pdf"
GOLDEN_JSON = REPO_ROOT / "tests" / "golden" / "golden-target.json"
SOURCE_PDF = REPO_ROOT / "tests" / "fixtures" / "test-hindi-10page.pdf"

_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_REPLACEMENT_CHAR = "\ufffd"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def golden() -> dict:
    with open(GOLDEN_JSON) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def pipeline_pages() -> list[str]:
    """Extract per-page text from the pipeline output PDF."""
    if not PIPELINE_PDF.exists():
        pytest.skip(f"Pipeline output not found: {PIPELINE_PDF}")
    doc = fitz.open(str(PIPELINE_PDF))
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()
    return pages


@pytest.fixture(scope="module")
def pipeline_text(pipeline_pages: list[str]) -> str:
    return "\n".join(pipeline_pages)


@pytest.fixture(scope="module")
def golden_pages() -> list[str]:
    """Extract per-page text from the golden reference PDF."""
    if not GOLDEN_PDF.exists():
        pytest.skip(f"Golden PDF not found: {GOLDEN_PDF}")
    doc = fitz.open(str(GOLDEN_PDF))
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()
    return pages


@pytest.fixture(scope="module")
def golden_text(golden_pages: list[str]) -> str:
    return "\n".join(golden_pages)


def _extract_body_chapter_title(full_text: str, ch_num: int) -> str | None:
    """Extract the chapter heading from the document body (not ToC).

    Handles titles that wrap across multiple lines in the PDF by joining
    the "Chapter N:" line with subsequent short lines that look like
    heading continuations (not body prose).
    """
    lines = full_text.split("\n")
    pattern = re.compile(rf"^Chapter\s+{ch_num}\s*:")
    # Find all matching line indices (ToC + body)
    indices = [i for i, line in enumerate(lines) if pattern.match(line.strip())]
    if not indices:
        return None
    # Take the LAST match (body heading, not ToC)
    idx = indices[-1]
    title_parts = [lines[idx].strip()]
    # Gather continuation lines that are short heading fragments
    for j in range(idx + 1, min(idx + 4, len(lines))):
        candidate = lines[j].strip()
        if not candidate:
            break
        # Stop if it looks like body prose: starts lowercase, or > 50 chars
        if candidate[0].islower() or len(candidate) > 50:
            break
        # Stop if it looks like another chapter heading
        if re.match(r"Chapter\s+\d+\s*:", candidate):
            break
        title_parts.append(candidate)
    return " ".join(title_parts)


# ===================================================================
# 1. Chapter Title Completeness
# ===================================================================


class TestChapterTitleCompleteness:
    """Verify chapter titles in the pipeline PDF match the golden reference
    full_title (including subtitles after the em-dash)."""

    def test_all_chapters_have_titles_in_body(
        self, golden: dict, pipeline_text: str
    ) -> None:
        missing = []
        for ch in golden["chapters"]:
            title = _extract_body_chapter_title(pipeline_text, ch["number"])
            if title is None:
                missing.append(ch["number"])
        assert not missing, f"Chapters missing from body: {missing}"

    @pytest.mark.parametrize("ch_idx", range(9))
    def test_chapter_title_not_truncated(
        self, ch_idx: int, golden: dict, pipeline_text: str
    ) -> None:
        """Each body chapter heading must contain at least 80% of the
        golden full_title's words (catches subtitle truncation)."""
        ch = golden["chapters"][ch_idx]
        expected_full = ch["full_title"]
        actual = _extract_body_chapter_title(pipeline_text, ch["number"])
        assert actual is not None, f"Chapter {ch['number']} heading not found"

        expected_words = set(expected_full.lower().split())
        actual_words = set(actual.lower().split())
        overlap = expected_words & actual_words
        coverage = len(overlap) / max(len(expected_words), 1)

        assert coverage >= 0.80, (
            f"Chapter {ch['number']} title truncated — "
            f"coverage {coverage:.0%} (<80%)\n"
            f"  Expected: {expected_full}\n"
            f"  Got:      {actual}"
        )

    def test_golden_pdf_titles_match_golden_json(
        self, golden: dict, golden_text: str
    ) -> None:
        """Sanity: golden PDF titles should match golden JSON full_titles."""
        for ch in golden["chapters"]:
            title = _extract_body_chapter_title(golden_text, ch["number"])
            if title is None:
                pytest.fail(f"Golden PDF missing chapter {ch['number']}")
            expected_words = set(ch["full_title"].lower().split())
            actual_words = set(title.lower().split())
            overlap = expected_words & actual_words
            coverage = len(overlap) / max(len(expected_words), 1)
            assert coverage >= 0.80, (
                f"Golden PDF chapter {ch['number']} doesn't match JSON: "
                f"{title!r} vs {ch['full_title']!r}"
            )


# ===================================================================
# 2. Content Coverage
# ===================================================================


class TestContentCoverage:
    """Per-chapter word counts must be within tolerance of golden target."""

    @pytest.mark.parametrize("ch_idx", range(9))
    def test_chapter_word_count_above_80_pct(
        self, ch_idx: int, golden: dict, pipeline_pages: list[str]
    ) -> None:
        ch = golden["chapters"][ch_idx]
        ch_num = ch["number"]
        expected_words = ch["word_count_approx"]
        next_ch = ch_num + 1

        # Skip cover (p1), ToC (p2), foreword (p3-4) — body starts at page 5
        body = "\n".join(pipeline_pages[4:])
        pattern = re.compile(
            rf"Chapter\s+{ch_num}\s*:.*?(?=Chapter\s+{next_ch}\s*:|Glossary|$)",
            re.DOTALL,
        )
        match = pattern.search(body)
        assert match is not None, f"Chapter {ch_num} not found in pipeline body"

        actual_words = len(match.group().split())
        ratio = actual_words / max(expected_words, 1)
        assert ratio >= 0.80, (
            f"Chapter {ch_num}: {actual_words} words is only "
            f"{ratio:.0%} of expected {expected_words} (<80%)"
        )

    def test_total_word_count_reasonable(
        self, golden: dict, pipeline_text: str
    ) -> None:
        """Total pipeline word count should be within 50%–200% of golden total."""
        golden_total = sum(ch["word_count_approx"] for ch in golden["chapters"])
        actual_total = len(pipeline_text.split())
        ratio = actual_total / max(golden_total, 1)
        assert 0.50 <= ratio <= 2.0, (
            f"Total word count {actual_total} is {ratio:.0%} of golden "
            f"{golden_total} — outside [50%, 200%] range"
        )


# ===================================================================
# 3. Script Hygiene
# ===================================================================


class TestScriptHygiene:
    """No stray Devanagari in English body sections (glossary excepted)."""

    def test_no_devanagari_in_body_text(
        self, pipeline_text: str
    ) -> None:
        """Body text (before glossary) should have <2% Devanagari chars
        after removing inline preserved terms in parentheses."""
        glossary_start = pipeline_text.rfind("Glossary")
        body = pipeline_text[:glossary_start] if glossary_start > 0 else pipeline_text
        # Remove allowed Devanagari in parens
        cleaned = re.sub(r"\([\u0900-\u097F\s]+\)", "", body)
        dev_count = len(_DEVANAGARI_RE.findall(cleaned))
        total = max(len(cleaned.replace(" ", "").replace("\n", "")), 1)
        ratio = dev_count / total
        assert ratio <= 0.02, (
            f"Devanagari in body: {dev_count} chars ({ratio:.1%}), max 2%"
        )

    def test_no_devanagari_sentences_in_english_chapters(
        self, pipeline_text: str
    ) -> None:
        """Flag any stretch of 10+ consecutive Devanagari characters in body
        (indicates an untranslated sentence leaked through)."""
        glossary_start = pipeline_text.rfind("Glossary")
        body = pipeline_text[:glossary_start] if glossary_start > 0 else pipeline_text
        # Remove inline preserved terms in parens
        cleaned = re.sub(r"\([\u0900-\u097F\s]+\)", "", body)
        long_dev = re.findall(r"[\u0900-\u097F]{10,}", cleaned)
        assert not long_dev, (
            f"Found {len(long_dev)} Devanagari sentence fragment(s) in body: "
            f"{[s[:30] for s in long_dev[:5]]}"
        )


# ===================================================================
# 4. Structural Alignment
# ===================================================================


class TestStructuralAlignment:
    """Pipeline output must match the expected document structure."""

    def test_chapter_count_matches_golden(
        self, golden: dict, pipeline_text: str
    ) -> None:
        expected = len(golden["chapters"])
        matches = re.findall(r"Chapter\s+(\d+)\s*:", pipeline_text)
        actual = sorted(set(int(n) for n in matches))
        assert len(actual) == expected, (
            f"Chapter count: found {len(actual)}, expected {expected}. "
            f"Numbers: {actual}"
        )

    def test_chapter_ordering_sequential(
        self, golden: dict, pipeline_text: str
    ) -> None:
        expected = list(range(1, len(golden["chapters"]) + 1))
        matches = re.findall(r"Chapter\s+(\d+)\s*:", pipeline_text)
        actual = sorted(set(int(n) for n in matches))
        assert actual == expected, (
            f"Chapters not sequential: {actual} vs {expected}"
        )

    def test_cover_page_present(self, pipeline_pages: list[str]) -> None:
        assert len(pipeline_pages) >= 1, "PDF has no pages"
        cover = pipeline_pages[0]
        assert cover.strip(), "Cover page (page 1) is empty"

    def test_toc_present(self, pipeline_text: str) -> None:
        assert "Table of Contents" in pipeline_text, "Table of Contents not found"

    def test_foreword_present(self, pipeline_text: str) -> None:
        assert re.search(r"Foreword", pipeline_text, re.IGNORECASE), (
            "Translator's Foreword not found"
        )

    def test_glossary_section_present(self, pipeline_text: str) -> None:
        assert re.search(r"Glossary", pipeline_text), "Glossary section not found"

    def test_all_required_sections_present(
        self, golden: dict, pipeline_text: str
    ) -> None:
        """Every required section from golden target must appear."""
        missing = []
        for section in golden["structure"]["expected_sections"]:
            if not section.get("required"):
                continue
            stype = section["type"]
            if stype == "cover":
                if not pipeline_text.strip():
                    missing.append("cover")
            elif stype == "toc":
                if "Table of Contents" not in pipeline_text:
                    missing.append("toc")
            elif stype == "foreword":
                if not re.search(r"Foreword", pipeline_text, re.IGNORECASE):
                    missing.append("foreword")
            elif stype == "glossary":
                if "Glossary" not in pipeline_text:
                    missing.append("glossary")
            elif stype == "chapter":
                ch_num = section.get("number")
                if ch_num and not re.search(
                    rf"Chapter\s+{ch_num}\s*:", pipeline_text
                ):
                    missing.append(f"chapter {ch_num}")
        assert not missing, f"Missing required sections: {missing}"


# ===================================================================
# 5. Garbled Text Detection
# ===================================================================


class TestGarbledTextDetection:
    """Detect encoding errors, OCR artifacts, and corrupted text."""

    def test_no_replacement_characters(self, pipeline_text: str) -> None:
        count = pipeline_text.count(_REPLACEMENT_CHAR)
        assert count == 0, f"Found {count} U+FFFD replacement characters"

    def test_no_null_bytes(self) -> None:
        if not PIPELINE_PDF.exists():
            pytest.skip("Pipeline PDF not found")
        doc = fitz.open(str(PIPELINE_PDF))
        for i in range(doc.page_count):
            text = doc[i].get_text()
            assert "\x00" not in text, f"Null byte in extracted text on page {i+1}"
        doc.close()

    def test_no_encoding_error_sequences(self, pipeline_text: str) -> None:
        """Check for common encoding error patterns: sequences of ? or
        diamond-question-mark sequences."""
        # Multiple consecutive ?s suggest encoding failures
        bad_runs = re.findall(r"\?{3,}", pipeline_text)
        assert not bad_runs, (
            f"Found {len(bad_runs)} runs of consecutive '?' characters "
            "(possible encoding errors)"
        )

    def test_no_excessive_symbol_sequences(self, pipeline_text: str) -> None:
        """Sequences of 5+ non-alphanumeric, non-space, non-punctuation chars
        suggest garbled data."""
        # Common punctuation and formatting chars are OK
        garbled = re.findall(
            r"[^\w\s.,;:!?'\"\-—–()[\]{}/\\@#$%&*+=<>|~`\u0900-\u097F]{5,}",
            pipeline_text,
        )
        assert not garbled, (
            f"Found {len(garbled)} suspicious symbol sequences: "
            f"{[g[:20] for g in garbled[:5]]}"
        )

    def test_no_ocr_fragment_words(self, pipeline_text: str) -> None:
        """Flag unusually high ratio of 1-2 character 'words' (OCR fragments).
        Allow up to 15% single-char words (articles, etc.)."""
        words = pipeline_text.split()
        if len(words) < 50:
            pytest.skip("Too little text to analyze")
        single_char = [w for w in words if len(w) == 1 and w.isalpha()]
        ratio = len(single_char) / len(words)
        assert ratio <= 0.15, (
            f"{len(single_char)}/{len(words)} single-char words "
            f"({ratio:.0%}), max 15%"
        )


# ===================================================================
# 6. ToC Accuracy
# ===================================================================


class TestTocAccuracy:
    """Table of Contents entries must match actual chapter titles in body."""

    def _get_toc_text(self, pipeline_pages: list[str]) -> str:
        """Extract ToC text from the ToC page (page 2)."""
        # ToC is on page 2 (index 1). It contains "Table of Contents"
        # followed by chapter entries until the page ends.
        for page in pipeline_pages[:3]:
            if "Table of Contents" in page:
                return page
        return ""

    def test_toc_has_entries(self, pipeline_pages: list[str]) -> None:
        toc_text = self._get_toc_text(pipeline_pages)
        assert toc_text, "Could not find ToC page"
        chapter_refs = re.findall(r"Chapter\s+\d+", toc_text)
        assert len(chapter_refs) >= 1, "ToC has no chapter entries"

    def test_toc_entry_count_matches_chapters(
        self, golden: dict, pipeline_pages: list[str]
    ) -> None:
        toc_text = self._get_toc_text(pipeline_pages)
        if not toc_text:
            pytest.fail("Could not find ToC page")
        toc_chapters = sorted(
            set(int(n) for n in re.findall(r"Chapter\s+(\d+)", toc_text))
        )
        expected = list(range(1, len(golden["chapters"]) + 1))
        assert toc_chapters == expected, (
            f"ToC chapters {toc_chapters} don't match expected {expected}"
        )

    @pytest.mark.parametrize("ch_idx", range(9))
    def test_toc_entry_contains_chapter_short_title(
        self, ch_idx: int, golden: dict, pipeline_pages: list[str]
    ) -> None:
        """Each ToC entry should contain at least the short title."""
        ch = golden["chapters"][ch_idx]
        toc_text = self._get_toc_text(pipeline_pages)
        if not toc_text:
            pytest.fail("Could not find ToC page")
        toc_lower = toc_text.lower()
        short_title = ch["title"].lower()
        assert short_title in toc_lower, (
            f"ToC missing title for Ch{ch['number']}: '{ch['title']}'"
        )


# ===================================================================
# 7. Glossary Consistency
# ===================================================================


class TestGlossaryConsistency:
    """Preserved cultural terms must appear consistently and cleanly."""

    def test_required_terms_present(
        self, golden: dict, pipeline_text: str
    ) -> None:
        required = golden["glossary"]["required_terms"]
        lower_text = pipeline_text.lower()
        missing = [
            t["term"] for t in required if t["term"].lower() not in lower_text
        ]
        assert not missing, f"Missing required glossary terms: {missing}"

    def test_glossary_terms_not_garbled(self, pipeline_text: str) -> None:
        """Glossary entries (term + Devanagari) should not contain U+FFFD."""
        glossary_start = pipeline_text.rfind("Glossary")
        if glossary_start < 0:
            pytest.skip("No glossary section found")
        glossary_text = pipeline_text[glossary_start:]
        assert _REPLACEMENT_CHAR not in glossary_text, (
            "Glossary section contains U+FFFD replacement characters"
        )

    def test_glossary_has_minimum_entries(
        self, golden: dict, pipeline_text: str
    ) -> None:
        min_entries = golden["glossary"]["min_entries"]
        # Count entries by pattern: "term (devanagari)"
        entries = re.findall(
            r"[a-z][a-z ]+\s*\([\u0900-\u097F]", pipeline_text
        )
        assert len(entries) >= min_entries, (
            f"Glossary has {len(entries)} entries, minimum {min_entries}"
        )

    def test_no_mixed_script_terms(self, pipeline_text: str) -> None:
        """Glossary Devanagari fields should not contain Latin characters."""
        glossary_start = pipeline_text.rfind("Glossary")
        if glossary_start < 0:
            pytest.skip("No glossary section found")
        glossary_text = pipeline_text[glossary_start:]
        # Find Devanagari strings in parentheses
        dev_fields = re.findall(r"\(([\u0900-\u097F\s]+)\)", glossary_text)
        mixed = [
            d for d in dev_fields if re.search(r"[A-Za-z]", d)
        ]
        assert not mixed, (
            f"Found {len(mixed)} mixed-script glossary entries: "
            f"{mixed[:5]}"
        )

    @pytest.mark.parametrize(
        "term",
        ["dharma", "karma", "yoga", "moksha", "guru", "seva", "sangat", "langar"],
    )
    def test_preserved_term_appears_in_text(
        self, term: str, pipeline_text: str
    ) -> None:
        """Key cultural terms must appear at least once."""
        assert term.lower() in pipeline_text.lower(), (
            f"Preserved term '{term}' not found in pipeline output"
        )


# ===================================================================
# 8. Paragraph Integrity
# ===================================================================


class TestParagraphIntegrity:
    """Detect broken content blocks or missing line breaks."""

    def test_no_suspiciously_short_content_paragraphs(
        self, pipeline_text: str
    ) -> None:
        """Flag content paragraphs with <10 words.
        Exclude known short items: headings, ToC entries, page numbers."""
        glossary_start = pipeline_text.rfind("Glossary")
        body = pipeline_text[:glossary_start] if glossary_start > 0 else pipeline_text

        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        short_content = []
        for p in paragraphs:
            words = p.split()
            wc = len(words)
            if wc < 3:
                continue  # Page numbers, single-word headings are fine
            if wc < 10:
                # Skip lines that look like headings
                if re.match(r"^(Chapter\s+\d+|Table of Contents|Foreword|Glossary)", p):
                    continue
                # Skip lines that are clearly ToC entries
                if re.match(r"^Chapter\s+\d+\s*:", p) and wc < 15:
                    continue
                short_content.append(p[:80])

        # Allow a few short paragraphs (transitions, epigraphs)
        assert len(short_content) <= 5, (
            f"Found {len(short_content)} suspiciously short paragraphs "
            f"(<10 words): {short_content[:5]}"
        )

    def test_no_excessively_long_paragraphs(
        self, pipeline_text: str
    ) -> None:
        """Paragraphs over 1000 words likely indicate missing line breaks."""
        paragraphs = [p.strip() for p in pipeline_text.split("\n\n") if p.strip()]
        long_paras = [
            (len(p.split()), p[:60]) for p in paragraphs if len(p.split()) > 1000
        ]
        assert not long_paras, (
            f"Found {len(long_paras)} excessively long paragraphs "
            f"(>1000 words): {long_paras[:3]}"
        )

    def test_chapter_content_not_empty(
        self, golden: dict, pipeline_pages: list[str]
    ) -> None:
        """Every chapter must have at least some body text after the heading."""
        # Skip cover, ToC, foreword — body starts at page 5 (index 4)
        body = "\n".join(pipeline_pages[4:])
        for ch in golden["chapters"]:
            ch_num = ch["number"]
            next_ch = ch_num + 1
            pattern = re.compile(
                rf"Chapter\s+{ch_num}\s*:.*?(?=Chapter\s+{next_ch}\s*:|Glossary|$)",
                re.DOTALL,
            )
            match = pattern.search(body)
            assert match is not None, f"Chapter {ch_num} not found in body"
            # Remove heading, check remaining content
            content = re.sub(r"Chapter\s+\d+\s*:[^\n]*", "", match.group())
            words = content.split()
            assert len(words) >= 20, (
                f"Chapter {ch_num} has only {len(words)} words of body content"
            )
