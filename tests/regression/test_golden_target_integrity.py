"""Standalone golden target integrity tests.

Validates the golden-target.json artifact is itself clean and complete,
independent of any gate logic.  These tests catch corruption in the
reference *before* it silently poisons Gate 6 comparisons.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_TARGET = REPO_ROOT / "tests" / "golden" / "golden-target.json"

_REPLACEMENT_CHAR = "\ufffd"


@pytest.fixture()
def golden() -> dict:
    """Load the golden target JSON once per test."""
    with open(GOLDEN_TARGET) as f:
        return json.load(f)


# ===================================================================
# 1. File-level checks
# ===================================================================


class TestGoldenTargetFileIntegrity:
    """Verify the golden-target.json file itself is sound."""

    def test_file_exists(self) -> None:
        assert GOLDEN_TARGET.exists(), "golden-target.json not found"

    def test_file_is_valid_json(self) -> None:
        with open(GOLDEN_TARGET) as f:
            data = json.load(f)
        assert isinstance(data, dict)

    def test_no_replacement_characters_in_file(self) -> None:
        """U+FFFD anywhere in the file means garbled/corrupt data."""
        raw = GOLDEN_TARGET.read_text(encoding="utf-8")
        fffd_positions = [i for i, c in enumerate(raw) if c == _REPLACEMENT_CHAR]
        assert len(fffd_positions) == 0, (
            f"Found {len(fffd_positions)} U+FFFD replacement chars at "
            f"byte offsets {fffd_positions[:10]}"
        )

    def test_no_null_bytes_in_file(self) -> None:
        raw = GOLDEN_TARGET.read_bytes()
        assert b"\x00" not in raw, "File contains null bytes — likely binary corruption"


# ===================================================================
# 2. Chapter completeness
# ===================================================================


class TestGoldenTargetChapters:
    """Every chapter must be present and have substantive content fields."""

    def test_chapter_count_is_nine(self, golden: dict) -> None:
        chapters = golden.get("chapters", [])
        assert len(chapters) == 9, f"Expected 9 chapters, got {len(chapters)}"

    def test_chapters_are_sequential(self, golden: dict) -> None:
        numbers = [ch["number"] for ch in golden["chapters"]]
        assert numbers == list(range(1, 10)), f"Non-sequential: {numbers}"

    def test_every_chapter_has_nonempty_title(self, golden: dict) -> None:
        for ch in golden["chapters"]:
            title = ch.get("title", "")
            assert title and title.strip(), (
                f"Chapter {ch.get('number')} has empty title"
            )

    def test_every_chapter_has_positive_word_count(self, golden: dict) -> None:
        for ch in golden["chapters"]:
            wc = ch.get("word_count_approx", 0)
            assert isinstance(wc, (int, float)) and wc > 0, (
                f"Chapter {ch.get('number')} word_count_approx={wc}"
            )

    def test_no_garbled_text_in_chapter_titles(self, golden: dict) -> None:
        for ch in golden["chapters"]:
            title = str(ch.get("title", ""))
            full = str(ch.get("full_title", ""))
            assert _REPLACEMENT_CHAR not in title, (
                f"Chapter {ch['number']} title has U+FFFD"
            )
            assert _REPLACEMENT_CHAR not in full, (
                f"Chapter {ch['number']} full_title has U+FFFD"
            )

    def test_no_garbled_text_in_key_phrases(self, golden: dict) -> None:
        for ch in golden["chapters"]:
            for phrase in ch.get("key_phrases", []):
                assert _REPLACEMENT_CHAR not in str(phrase), (
                    f"Chapter {ch['number']} key_phrase '{phrase}' has U+FFFD"
                )


# ===================================================================
# 3. Cover page / structure
# ===================================================================


class TestGoldenTargetStructure:
    """Structural metadata must be present and correct."""

    def test_cover_section_present(self, golden: dict) -> None:
        types = [s["type"] for s in golden["structure"]["expected_sections"]]
        assert "cover" in types, "Cover section missing from structure"

    def test_toc_section_present(self, golden: dict) -> None:
        types = [s["type"] for s in golden["structure"]["expected_sections"]]
        assert "toc" in types, "ToC section missing from structure"

    def test_cover_is_required(self, golden: dict) -> None:
        cover = next(
            s for s in golden["structure"]["expected_sections"]
            if s["type"] == "cover"
        )
        assert cover.get("required") is True

    def test_glossary_section_present(self, golden: dict) -> None:
        types = [s["type"] for s in golden["structure"]["expected_sections"]]
        assert "glossary" in types, "Glossary section missing"

    def test_page_count_thresholds_defined(self, golden: dict) -> None:
        thresholds = golden.get("quality_thresholds", {})
        assert "page_count_ratio_max" in thresholds
        assert "word_count_tolerance" in thresholds
        assert thresholds["page_count_ratio_max"] > 1.0
        assert 0 < thresholds["word_count_tolerance"] < 1.0


# ===================================================================
# 4. Glossary requirements
# ===================================================================


class TestGoldenTargetGlossary:
    """Glossary config must be well-formed."""

    def test_required_terms_present(self, golden: dict) -> None:
        terms = golden["glossary"]["required_terms"]
        assert len(terms) >= 10, f"Only {len(terms)} required terms"

    def test_required_terms_have_names(self, golden: dict) -> None:
        for t in golden["glossary"]["required_terms"]:
            assert t.get("term") and t["term"].strip(), (
                f"Empty term entry: {t}"
            )

    def test_no_garbled_text_in_glossary_terms(self, golden: dict) -> None:
        for t in golden["glossary"]["required_terms"]:
            assert _REPLACEMENT_CHAR not in str(t.get("term", "")), (
                f"Glossary term '{t}' contains U+FFFD"
            )

    def test_min_entries_threshold_reasonable(self, golden: dict) -> None:
        assert golden["glossary"]["min_entries"] >= 10
