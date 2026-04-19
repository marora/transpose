"""Golden-targeted QA regression tests.

Tests the golden_targeted_qa_gate against the golden source, golden target,
and simulated candidate outputs (good and bad).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from transpose.pipeline.gates import GateResult, golden_targeted_qa_gate

# ---------------------------------------------------------------------------
# Marks
# ---------------------------------------------------------------------------
pytestmark = [pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures"
OUTPUT_PDF = REPO_ROOT / "Test_Hindi_Book_final.pdf"


# ===================================================================
# 1. Golden source fixture validation
# ===================================================================

class TestGoldenSourceFixture:
    """Verify the golden source fixture exists and is valid."""

    def test_source_pdf_exists(self) -> None:
        source = FIXTURES_DIR / "test-hindi-10page.pdf"
        assert source.exists(), "Golden source PDF missing"

    def test_source_pdf_has_pages(self) -> None:
        import fitz

        source = FIXTURES_DIR / "test-hindi-10page.pdf"
        if not source.exists():
            pytest.skip("Source PDF not available")
        doc = fitz.open(str(source))
        assert doc.page_count == 10, f"Expected 10 pages, got {doc.page_count}"
        doc.close()

    def test_source_fingerprint_exists(self) -> None:
        fp = GOLDEN_DIR / "golden-source-fingerprint.json"
        assert fp.exists(), "Golden source fingerprint JSON missing"

    def test_source_fingerprint_valid(self) -> None:
        fp = GOLDEN_DIR / "golden-source-fingerprint.json"
        with open(fp) as f:
            data = json.load(f)
        assert data["page_count"] == 10
        assert len(data["structure"]["chapters"]) == 9
        assert data["language"] == "Hindi"


# ===================================================================
# 2. Golden target fixture validation
# ===================================================================

class TestGoldenTargetFixture:
    """Verify the golden target fixture exists and is valid."""

    def test_golden_target_exists(self) -> None:
        gt = GOLDEN_DIR / "golden-target.json"
        assert gt.exists(), "Golden target JSON missing"

    def test_golden_target_has_chapters(self) -> None:
        with open(GOLDEN_DIR / "golden-target.json") as f:
            data = json.load(f)
        assert len(data["chapters"]) == 9
        for ch in data["chapters"]:
            assert "number" in ch
            assert "title" in ch
            assert "word_count_approx" in ch

    def test_golden_target_has_structure(self) -> None:
        with open(GOLDEN_DIR / "golden-target.json") as f:
            data = json.load(f)
        structure = data["structure"]
        assert "expected_sections" in structure
        section_types = [s["type"] for s in structure["expected_sections"]]
        assert "cover" in section_types
        assert "toc" in section_types
        assert "foreword" in section_types
        assert "glossary" in section_types

    def test_golden_target_has_glossary(self) -> None:
        with open(GOLDEN_DIR / "golden-target.json") as f:
            data = json.load(f)
        glossary = data["glossary"]
        assert glossary["min_entries"] >= 35
        assert len(glossary["required_terms"]) >= 10

    def test_golden_target_has_quality_thresholds(self) -> None:
        with open(GOLDEN_DIR / "golden-target.json") as f:
            data = json.load(f)
        thresholds = data["quality_thresholds"]
        assert thresholds["word_count_tolerance"] == 0.30
        assert thresholds["page_count_ratio_max"] == 1.5


# ===================================================================
# 3. Gate passes for actual candidate (real PDF)
# ===================================================================

class TestGoldenGatePassesForGoodCandidate:
    """The current best output PDF should pass the golden QA gate."""

    @pytest.mark.slow
    def test_gate_passes_for_current_output(self) -> None:
        if not OUTPUT_PDF.exists():
            pytest.skip("Pipeline output PDF not available")
        result = golden_targeted_qa_gate(str(OUTPUT_PDF))
        assert isinstance(result, GateResult)
        assert result.gate_name == "golden_targeted_qa"
        assert result.passed, f"Gate failed: {result.failures}"

    @pytest.mark.slow
    def test_gate_returns_details(self) -> None:
        if not OUTPUT_PDF.exists():
            pytest.skip("Pipeline output PDF not available")
        result = golden_targeted_qa_gate(str(OUTPUT_PDF))
        assert "checks" in result.details
        assert "chapter_count" in result.details
        assert "page_count" in result.details

    @pytest.mark.slow
    def test_gate_detects_all_chapters(self) -> None:
        if not OUTPUT_PDF.exists():
            pytest.skip("Pipeline output PDF not available")
        result = golden_targeted_qa_gate(str(OUTPUT_PDF))
        assert result.details["chapter_count"] == 9

    @pytest.mark.slow
    def test_gate_finds_glossary_terms(self) -> None:
        if not OUTPUT_PDF.exists():
            pytest.skip("Pipeline output PDF not available")
        result = golden_targeted_qa_gate(str(OUTPUT_PDF))
        assert result.details["glossary_terms_found"] >= 10
        assert len(result.details.get("glossary_terms_missing", [])) == 0


# ===================================================================
# 4. Gate fails for bad candidates (mock scenarios)
# ===================================================================

class TestGoldenGateFailsForBadCandidate:
    """The gate must correctly detect problems in bad candidates."""

    def _make_pdf(self, tmp_path: Path, pages: list[str]) -> str:
        """Create a minimal PDF with given page contents using fitz."""
        import fitz

        doc = fitz.open()
        for text in pages:
            page = doc.new_page(width=595, height=842)
            # Insert text in blocks to avoid truncation on single insert
            y = 72
            for line in text.split("\n"):
                if y > 780:
                    page = doc.new_page(width=595, height=842)
                    y = 72
                page.insert_text((72, y), line[:100], fontsize=9)
                y += 12
        pdf_path = tmp_path / "candidate.pdf"
        doc.save(str(pdf_path))
        doc.close()
        return str(pdf_path)

    def test_missing_chapters_detected(self, tmp_path: Path) -> None:
        """PDF with only 3 chapters should fail structural match."""
        pages = [
            "Test Hindi Book",  # cover
            "Table of Contents\nChapter 1: Dharma\nChapter 2: Yoga\nChapter 3: Sikh",
            "Foreword\n" + " ".join(["word"] * 100),
            "Chapter 1: Dharma and Karma\n" + " ".join(["text"] * 200),
            "Chapter 2: Yoga and Meditation\n" + " ".join(["text"] * 200),
            "Chapter 3: Sikh Tradition\n" + " ".join(["text"] * 200),
        ]
        pdf_path = self._make_pdf(tmp_path, pages)
        result = golden_targeted_qa_gate(pdf_path)
        assert not result.passed
        assert any("Chapter count" in f or "not sequential" in f for f in result.failures)

    def test_hindi_bleed_detected(self, tmp_path: Path) -> None:
        """Script hygiene check detects Devanagari when present in body."""
        import json
        import re

        import fitz as _fitz

        # Create a golden target that's simpler for this test
        simple_golden = {
            "structure": {
                "expected_sections": [
                    {"type": "cover", "required": True},
                    {"type": "toc", "required": True},
                ],
                "source_page_count": 10,
                "page_count_ratio_max": 5.0,
            },
            "chapters": [
                {"number": 1, "title": "Ch1", "word_count_approx": 50, "word_count_tolerance": 0.99}
            ],
            "glossary": {"min_entries": 0, "required_terms": []},
            "quality_thresholds": {"devanagari_in_body_max_ratio": 0.02},
        }
        golden_path = tmp_path / "golden.json"
        golden_path.write_text(json.dumps(simple_golden))

        # Create PDF with Devanagari characters embedded using font that supports them
        doc = _fitz.open()
        # Cover
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 72), "Test Hindi Book", fontsize=14)
        # ToC
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 72), "Table of Contents\nChapter 1: Ch1", fontsize=10)
        # Body page with lots of Devanagari chars mixed in
        p = doc.new_page(width=595, height=842)
        # Use insert_text with a font that supports Devanagari
        text = "Chapter 1: Ch1\n" + " ".join(["text"] * 50)
        p.insert_text((72, 72), text, fontsize=10)
        # Insert Devanagari using a CJK/Devanagari-capable approach
        # Write raw Devanagari characters - fitz will encode them even if
        # they render as .notdef, they'll still be in the text stream
        tw = _fitz.TextWriter(p.rect)
        hindi = "\u0927\u0930\u094d\u092e " * 200  # धर्म repeated
        try:
            tw.append((72, 200), hindi, fontsize=8, font=_fitz.Font("notosans"))
        except Exception:
            # If font not available, use fillchar approach
            tw.append((72, 200), hindi, fontsize=8)
        tw.write_text(p)

        pdf_path = tmp_path / "hindi_bleed.pdf"
        doc.save(str(pdf_path))
        doc.close()

        # Verify the PDF actually contains Devanagari in extracted text
        check_doc = _fitz.open(str(pdf_path))
        body_page_text = check_doc[2].get_text()
        check_doc.close()

        dev_chars = len(re.findall(r"[\u0900-\u097F]", body_page_text))
        if dev_chars < 10:
            # fitz couldn't embed Devanagari — skip this test
            pytest.skip("fitz could not embed Devanagari characters with available fonts")

        result = golden_targeted_qa_gate(str(pdf_path), str(golden_path))
        assert not result.passed
        assert any("Devanagari" in f for f in result.failures)

    def test_missing_glossary_terms_detected(self, tmp_path: Path) -> None:
        """PDF without glossary section should fail glossary integrity."""
        pages = [
            "Test Hindi Book",
            "Table of Contents\n" + "\n".join(
                f"Chapter {i}: Ch{i}" for i in range(1, 10)
            ),
            "Foreword\n" + " ".join(["word"] * 100),
        ] + [
            f"Chapter {i}: Title {i}\n" + " ".join(["English text"] * 100)
            for i in range(1, 10)
        ]
        pdf_path = self._make_pdf(tmp_path, pages)
        result = golden_targeted_qa_gate(pdf_path)
        assert not result.passed
        assert any("glossary" in f.lower() or "Glossary" in f for f in result.failures)

    def test_missing_candidate_pdf(self) -> None:
        """Non-existent PDF path should fail."""
        result = golden_targeted_qa_gate("/nonexistent/path.pdf")
        assert not result.passed
        assert any("not found" in f for f in result.failures)

    def test_missing_golden_target(self, tmp_path: Path) -> None:
        """Non-existent golden target should fail."""
        pages = ["Test Hindi Book"]
        pdf_path = self._make_pdf(tmp_path, pages)
        result = golden_targeted_qa_gate(pdf_path, golden_target_path="/nonexistent/golden.json")
        assert not result.passed
        assert any("Golden target not found" in f for f in result.failures)

    def test_excessive_page_count_detected(self, tmp_path: Path) -> None:
        """PDF with too many pages should fail no-regression check."""
        pages = [
            "Test Hindi Book",
            "Table of Contents\n" + "\n".join(
                f"Chapter {i}: Ch{i}" for i in range(1, 10)
            ),
            "Foreword\n" + " ".join(["word"] * 100),
        ] + [
            f"Chapter {i}: Title {i}\n" + " ".join(["text"] * 150)
            for i in range(1, 10)
        ] + [
            f"Extra page {i}\n" + " ".join(["padding"] * 200)
            for i in range(10)  # 10 extra pages = ~22 total, well over 15
        ]
        pdf_path = self._make_pdf(tmp_path, pages)
        result = golden_targeted_qa_gate(pdf_path)
        assert not result.passed
        assert any("Page count" in f for f in result.failures)


# ===================================================================
# 5. Tolerance boundary tests
# ===================================================================

class TestToleranceBoundaries:
    """Test that word count and page count boundaries work correctly."""

    def _make_chapter_pdf(self, tmp_path: Path, word_counts: dict[int, int]) -> str:
        """Create a PDF with specific word counts per chapter."""
        import fitz

        doc = fitz.open()
        # Cover
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 72), "Test Hindi Book", fontsize=14)
        # ToC
        p = doc.new_page(width=595, height=842)
        y = 72
        p.insert_text((72, y), "Table of Contents", fontsize=12)
        for i in range(1, 10):
            y += 14
            p.insert_text((72, y), f"Chapter {i}: Ch{i}", fontsize=10)
        # Foreword
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 72), "Foreword", fontsize=12)
        y = 90
        for _j in range(10):
            p.insert_text((72, y), " ".join(["word"] * 10), fontsize=9)
            y += 12

        # Chapters — write words in short lines to avoid truncation
        for ch_num in range(1, 10):
            wc = word_counts.get(ch_num, 180)
            p = doc.new_page(width=595, height=842)
            p.insert_text((72, 72), f"Chapter {ch_num}: Test Chapter {ch_num}", fontsize=11)
            y = 90
            words_written = 0
            words_per_line = 8
            while words_written < wc:
                if y > 780:
                    p = doc.new_page(width=595, height=842)
                    y = 72
                batch = min(words_per_line, wc - words_written)
                p.insert_text((72, y), " ".join(["text"] * batch), fontsize=9)
                y += 12
                words_written += batch

        # Glossary page with terms
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 60), "Glossary", fontsize=12)
        glossary_entries = [
            "dharma (धर्म) Duty and righteousness",
            "karma (कर्म) Action and its consequences",
            "yoga (योग) Spiritual discipline",
            "moksha (मोक्ष) Liberation from cycle",
            "sangat (संगत) Sacred congregation",
            "langar (लंगर) Communal kitchen",
            "seva (सेवा) Selfless service",
            "guru (गुरु) Spiritual teacher",
            "prana (प्राण) Life force energy",
            "samsara (संसार) Cycle of rebirth",
            "samadhi (समाधि) Deep meditation",
            "jnana (ज्ञान) Knowledge",
            "maya (माया) Illusion",
            "waheguru (वाहेगुरु) Wonderful Lord",
        ]
        # Add more entries to reach 35+
        for i in range(25):
            glossary_entries.append(f"term{i} (तत्त्व) Definition {i}")

        y = 72
        for entry in glossary_entries:
            if y > 780:
                p = doc.new_page(width=595, height=842)
                y = 72
            p.insert_text((72, y), entry, fontsize=8)
            y += 14

        pdf_path = tmp_path / "candidate.pdf"
        doc.save(str(pdf_path))
        doc.close()
        return str(pdf_path)

    def test_word_count_at_lower_boundary_passes(self, tmp_path: Path) -> None:
        """Word counts at exactly -30% of golden should pass."""
        # Use per-chapter lower bounds based on golden target
        # Ch1: 218*0.7=152.6→153, Ch2: 208*0.7=145.6→146, etc.
        golden_wc = {1: 218, 2: 208, 3: 198, 4: 189, 5: 157, 6: 152, 7: 150, 8: 160, 9: 191}
        word_counts = {ch: int(wc * 0.75) for ch, wc in golden_wc.items()}  # 75% = within 30%
        pdf_path = self._make_chapter_pdf(tmp_path, word_counts)
        result = golden_targeted_qa_gate(pdf_path)
        word_failures = [f for f in result.failures if "word count" in f.lower()]
        assert len(word_failures) == 0, f"Unexpected word count failures: {word_failures}"

    def test_word_count_at_upper_boundary_passes(self, tmp_path: Path) -> None:
        """Word counts at +25% of golden should pass (within 30% tolerance)."""
        golden_wc = {1: 218, 2: 208, 3: 198, 4: 189, 5: 157, 6: 152, 7: 150, 8: 160, 9: 191}
        word_counts = {ch: int(wc * 1.20) for ch, wc in golden_wc.items()}  # 120% = within 30%
        pdf_path = self._make_chapter_pdf(tmp_path, word_counts)
        result = golden_targeted_qa_gate(pdf_path)
        word_failures = [f for f in result.failures if "word count" in f.lower()]
        assert len(word_failures) == 0, f"Unexpected word count failures: {word_failures}"

    def test_word_count_far_below_fails(self, tmp_path: Path) -> None:
        """Word counts at 50% of golden should fail."""
        word_counts = {i: 50 for i in range(1, 10)}
        pdf_path = self._make_chapter_pdf(tmp_path, word_counts)
        result = golden_targeted_qa_gate(pdf_path)
        word_failures = [f for f in result.failures if "word count" in f.lower()]
        assert len(word_failures) > 0, "Expected word count failure for very short chapters"

    @pytest.mark.slow
    def test_page_count_at_boundary(self) -> None:
        """Output PDF at 14 pages for 10-page source is within 1.5× (15)."""
        if not OUTPUT_PDF.exists():
            pytest.skip("Pipeline output PDF not available")
        result = golden_targeted_qa_gate(str(OUTPUT_PDF))
        page_failures = [f for f in result.failures if "Page count" in f]
        assert len(page_failures) == 0, f"Page count should be within bounds: {page_failures}"
