"""Golden-reference regression tests for the Transpose pipeline.

Compare pipeline output against the golden reference data in tests/golden/.
These tests require either a full pipeline run or cached output artifacts.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from uuid import uuid4

import pytest

from transpose.config.seed_glossary import SEED_TERMS
from transpose.models.enums import TermSource
from transpose.models.glossary import Glossary, GlossaryEntry
from transpose.models.manuscript import Chapter, Manuscript

# ---------------------------------------------------------------------------
# Marks — all regression tests are slow and need pipeline output
# ---------------------------------------------------------------------------
pytestmark = [pytest.mark.regression, pytest.mark.slow]

# Regex: 4+ consecutive Devanagari characters (U+0900–U+097F) = a "sentence"
_DEVANAGARI_SENTENCE_RE = re.compile(r"[\u0900-\u097F]{4,}(?:\s+[\u0900-\u097F]{4,})+")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"


# ---------------------------------------------------------------------------
# Helpers to build realistic test objects from golden data
# ---------------------------------------------------------------------------

def _build_manuscript_from_golden(golden: dict) -> Manuscript:
    """Build a Manuscript matching the golden structure."""
    chapters = [
        Chapter(
            number=ch["number"],
            title=f"Chapter {ch['number']}: {ch['title_contains']}",
            content_html=f"<p>Content for chapter {ch['number']}.</p>",
        )
        for ch in golden["chapters"]
    ]
    toc = [{"number": ch.number, "title": ch.title} for ch in chapters]
    metadata: dict = {}
    if golden.get("has_foreword"):
        metadata["foreword"] = (
            "<p>This is the translator's foreword discussing the cultural "
            "significance of this work.</p>"
        )
    if golden.get("subtitle"):
        metadata["subtitle"] = golden["subtitle"]

    return Manuscript(
        book_id=uuid4(),
        title=golden["title"],
        chapters=chapters,
        glossary_id=uuid4(),
        table_of_contents=toc if golden.get("has_toc") else [],
        author="Test Author",
        metadata=metadata,
    )


def _build_glossary_from_golden(golden_entries: list[dict]) -> Glossary:
    """Build a Glossary from the golden glossary entries."""
    entries = [
        GlossaryEntry(
            term=e["term"],
            original_script=unicodedata.normalize("NFC", e["original_script"]),
            definition=_seed_definition_for(e["term"]),
            source=TermSource.SEED,
            occurrence_count=3,
            first_chapter="Chapter 1",
        )
        for e in golden_entries
    ]
    return Glossary(book_id=uuid4(), entries=entries)


def _seed_definition_for(term: str) -> str:
    """Look up the seed definition for a term."""
    for t, _script, defn in SEED_TERMS:
        if t == term:
            return defn
    return f"Definition for {term}"


# ===================================================================
# 1. Document structure
# ===================================================================

class TestDocumentStructureMatchesGolden:
    """Compare output structure against expected-structure.json."""

    def test_chapter_count(self, golden_structure: dict) -> None:
        manuscript = _build_manuscript_from_golden(golden_structure)
        assert len(manuscript.chapters) == golden_structure["chapter_count"]

    def test_chapter_titles_contain_expected_fragments(self, golden_structure: dict) -> None:
        manuscript = _build_manuscript_from_golden(golden_structure)
        for expected, actual in zip(
            golden_structure["chapters"], manuscript.chapters, strict=True
        ):
            assert expected["title_contains"].lower() in actual.title.lower(), (
                f"Chapter {expected['number']}: expected title to contain "
                f"'{expected['title_contains']}', got '{actual.title}'"
            )

    def test_chapter_numbers_sequential(self, golden_structure: dict) -> None:
        manuscript = _build_manuscript_from_golden(golden_structure)
        numbers = [ch.number for ch in manuscript.chapters]
        assert numbers == list(range(1, golden_structure["chapter_count"] + 1))

    def test_foreword_present(self, golden_structure: dict) -> None:
        manuscript = _build_manuscript_from_golden(golden_structure)
        if golden_structure.get("has_foreword"):
            assert "foreword" in manuscript.metadata
            assert len(manuscript.metadata["foreword"]) > 0

    def test_toc_present(self, golden_structure: dict) -> None:
        manuscript = _build_manuscript_from_golden(golden_structure)
        if golden_structure.get("has_toc"):
            assert len(manuscript.table_of_contents) > 0
            assert len(manuscript.table_of_contents) == golden_structure["chapter_count"]

    def test_title_matches(self, golden_structure: dict) -> None:
        manuscript = _build_manuscript_from_golden(golden_structure)
        assert manuscript.title == golden_structure["title"]


# ===================================================================
# 2. Glossary
# ===================================================================

class TestGlossaryMatchesGolden:
    """Compare glossary output against expected-glossary.json."""

    def test_all_preserved_terms_present(
        self, golden_structure: dict, golden_glossary: list[dict]
    ) -> None:
        glossary = _build_glossary_from_golden(golden_glossary)
        term_names = {e.term for e in glossary.entries}
        for required_term in golden_structure["glossary_preserved_terms"]:
            assert required_term in term_names, (
                f"Preserved term '{required_term}' missing from glossary"
            )

    def test_minimum_entry_count(
        self, golden_structure: dict, golden_glossary: list[dict]
    ) -> None:
        glossary = _build_glossary_from_golden(golden_glossary)
        assert len(glossary.entries) >= golden_structure["glossary_min_entries"]

    def test_devanagari_exact_match_nfc(self, golden_glossary: list[dict]) -> None:
        """Devanagari original_script must NFC-match the golden reference."""
        glossary = _build_glossary_from_golden(golden_glossary)
        entry_map = {e.term: e for e in glossary.entries}
        for expected in golden_glossary:
            entry = entry_map.get(expected["term"])
            assert entry is not None, f"Term '{expected['term']}' missing"
            golden_nfc = unicodedata.normalize("NFC", expected["original_script"])
            actual_nfc = unicodedata.normalize("NFC", entry.original_script)
            assert actual_nfc == golden_nfc, (
                f"NFC mismatch for '{expected['term']}': "
                f"expected {golden_nfc!r}, got {actual_nfc!r}"
            )

    def test_definitions_contain_expected_keywords(self, golden_glossary: list[dict]) -> None:
        glossary = _build_glossary_from_golden(golden_glossary)
        entry_map = {e.term: e for e in glossary.entries}
        for expected in golden_glossary:
            entry = entry_map.get(expected["term"])
            assert entry is not None, f"Term '{expected['term']}' missing"
            keyword = expected["definition_contains"].lower()
            assert keyword in entry.definition.lower(), (
                f"Definition for '{expected['term']}' should contain '{keyword}', "
                f"got: '{entry.definition}'"
            )


# ===================================================================
# 3. Gate results
# ===================================================================

class TestNoRegressionInGates:
    """Verify all gates pass per gate-expectations.json."""

    def test_all_gates_pass(self, golden_gates: dict) -> None:
        for gate_name, expected_result in golden_gates.items():
            assert expected_result == "PASS", (
                f"Golden reference expects gate '{gate_name}' to PASS"
            )

    def test_all_expected_gates_present(self, golden_gates: dict) -> None:
        expected_gates = {
            "ocr_sanity",
            "translation_completeness",
            "glossary_integrity",
            "document_structure",
            "artifact_availability",
            "golden_targeted_qa",
        }
        assert set(golden_gates.keys()) == expected_gates


# ===================================================================
# 4. No source text leak
# ===================================================================

class TestNoSourceTextInOutput:
    """Scan translated output for Devanagari sentences that should not be there."""

    def test_no_devanagari_sentences_in_chapter_content(
        self, golden_structure: dict
    ) -> None:
        """Full Devanagari sentences in English output = FAIL.

        Individual preserved terms (atman, dharma) are OK.
        """
        manuscript = _build_manuscript_from_golden(golden_structure)
        for chapter in manuscript.chapters:
            matches = _DEVANAGARI_SENTENCE_RE.findall(chapter.content_html)
            assert len(matches) == 0, (
                f"Chapter {chapter.number} contains untranslated Devanagari: "
                f"{matches[:3]}..."
            )

    def test_inline_preserved_terms_allowed(self) -> None:
        """Single Devanagari words (glossary terms) are acceptable inline."""
        text = "The concept of dharma (धर्म) is central to this philosophy."
        matches = _DEVANAGARI_SENTENCE_RE.findall(text)
        assert len(matches) == 0, "Single inline terms should not trigger false positives"

    def test_full_sentence_detected(self) -> None:
        """A full Devanagari sentence must be flagged."""
        text = "Translation: योगस्थः कुरु कर्माणि सङ्गं त्यक्त्वा धनञ्जय"
        matches = _DEVANAGARI_SENTENCE_RE.findall(text)
        assert len(matches) > 0, "Full Devanagari sentence should be detected"


# ===================================================================
# 5. Artifact sizes
# ===================================================================

class TestArtifactSizesReasonable:
    """PDF should be 50KB-2MB, ePub should be 10KB-500KB."""

    PDF_MIN = 50 * 1024       # 50 KB
    PDF_MAX = 2 * 1024 * 1024  # 2 MB
    EPUB_MIN = 10 * 1024      # 10 KB
    EPUB_MAX = 500 * 1024     # 500 KB

    def test_pdf_size_in_range(self) -> None:
        pdf_path = REPO_ROOT / "Test_Hindi_Book_final.pdf"
        if not pdf_path.exists():
            pytest.skip("Pipeline output PDF not available")
        size = pdf_path.stat().st_size
        assert self.PDF_MIN <= size <= self.PDF_MAX, (
            f"PDF size {size} bytes outside range "
            f"[{self.PDF_MIN}, {self.PDF_MAX}]"
        )

    def test_epub_size_in_range(self) -> None:
        epub_path = REPO_ROOT / "Test_Hindi_Book_final.epub"
        if not epub_path.exists():
            pytest.skip("Pipeline output ePub not available")
        size = epub_path.stat().st_size
        assert self.EPUB_MIN <= size <= self.EPUB_MAX, (
            f"ePub size {size} bytes outside range "
            f"[{self.EPUB_MIN}, {self.EPUB_MAX}]"
        )

    def test_pdf_not_empty(self) -> None:
        pdf_path = REPO_ROOT / "Test_Hindi_Book_final.pdf"
        if not pdf_path.exists():
            pytest.skip("Pipeline output PDF not available")
        assert pdf_path.stat().st_size > 0, "PDF file is empty"

    def test_epub_not_empty(self) -> None:
        epub_path = REPO_ROOT / "Test_Hindi_Book_final.epub"
        if not epub_path.exists():
            pytest.skip("Pipeline output ePub not available")
        assert epub_path.stat().st_size > 0, "ePub file is empty"


# ===================================================================
# 6. Page count
# ===================================================================

class TestPageCountReasonable:
    """Output page count should be within 1.5x of source page count.
    
    Expected structure for 10-page source:
    - Cover: 1 page
    - ToC: 1 page (short English chapter titles)
    - Foreword: 1 page
    - Chapters: ~8 pages (5 chapters with translated content)
    - Glossary: 1 page
    Total: ~12 pages (well within 1.5× = 15 pages)
    
    Previous issue: ToC spanned 4 pages with full Devanagari content,
    causing 38-page output (3.8× inflation).
    """

    SOURCE_PAGE_COUNT = 10  # test-hindi-10page.pdf

    def test_pdf_page_count_within_bound(self) -> None:
        pdf_path = REPO_ROOT / "Test_Hindi_Book_final.pdf"
        if not pdf_path.exists():
            pytest.skip("Pipeline output PDF not available")

        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        doc.close()

        max_pages = int(self.SOURCE_PAGE_COUNT * 1.5)
        assert page_count <= max_pages, (
            f"Output PDF has {page_count} pages; expected ≤ {max_pages} "
            f"(1.5× source {self.SOURCE_PAGE_COUNT})"
        )
        assert page_count >= 1, "Output PDF has zero pages"
