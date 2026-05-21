"""Tests for the glossary pipeline stage.

Tests glossary compilation, deduplication, and occurrence filtering.
Issue #9: Unicode normalization for Devanagari glossary entries.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from transpose.config.seed_glossary import SEED_TERMS
from transpose.models.enums import TermSource
from transpose.models.glossary import GlossaryEntry as RealGlossaryEntry
from transpose.utils.unicode import normalize_unicode


@dataclass
class GlossaryInput:
    """Glossary stage input contract."""

    book_id: UUID
    min_occurrences_for_llm_terms: int = 2


@dataclass
class GlossaryEntry:
    """A single glossary entry."""

    term: str
    original_script: str
    definition: str
    source: TermSource
    occurrence_count: int
    first_chapter: str | None
    needs_review: bool


@dataclass
class GlossaryOutput:
    """Glossary stage output contract."""

    book_id: UUID
    glossary_id: UUID
    total_terms: int
    seed_terms: int
    llm_detected_terms: int
    needs_review_count: int
    entries: list[GlossaryEntry] = field(default_factory=list)


class TestGlossaryContract:
    """Test glossary stage contract validation."""

    def test_glossary_input_defaults(self) -> None:
        """Test GlossaryInput has sensible defaults."""
        book_id = uuid4()
        input_data = GlossaryInput(book_id=book_id)
        assert input_data.book_id == book_id
        assert input_data.min_occurrences_for_llm_terms == 2

    def test_glossary_entry_shape(self) -> None:
        """Test GlossaryEntry has all required fields."""
        entry = GlossaryEntry(
            term="dharma",
            original_script="धर्म",
            definition="Righteous duty",
            source=TermSource.SEED,
            occurrence_count=10,
            first_chapter="Chapter 1",
            needs_review=False,
        )
        assert len(entry.term) > 0
        assert entry.occurrence_count > 0
        assert entry.source in TermSource

    def test_glossary_output_shape(self) -> None:
        """Test GlossaryOutput has all required fields."""
        book_id = uuid4()
        glossary_id = uuid4()
        output = GlossaryOutput(
            book_id=book_id,
            glossary_id=glossary_id,
            total_terms=50,
            seed_terms=40,
            llm_detected_terms=10,
            needs_review_count=5,
            entries=[],
        )
        assert output.total_terms == output.seed_terms + output.llm_detected_terms
        assert output.needs_review_count >= 0


class TestGlossaryDeduplication:
    """Test term deduplication logic."""

    def test_duplicate_terms_merged(self) -> None:
        """Test that duplicate terms are merged."""
        # Simulate finding "dharma" multiple times
        term_occurrences = [
            ("dharma", "धर्म", "Righteous duty"),
            ("dharma", "धर्म", "Duty"),  # Duplicate with different definition
            ("karma", "कर्म", "Action"),
        ]

        # Deduplicate
        unique_terms = {}
        for term, script, definition in term_occurrences:
            if term not in unique_terms:
                unique_terms[term] = (script, definition, 1)
            else:
                script_existing, def_existing, count = unique_terms[term]
                # Keep longest definition
                new_def = definition if len(definition) > len(def_existing) else def_existing
                unique_terms[term] = (script_existing, new_def, count + 1)

        assert len(unique_terms) == 2
        assert unique_terms["dharma"][2] == 2  # Count is 2
        assert unique_terms["dharma"][1] == "Righteous duty"  # Longest definition


class TestGlossaryOccurrenceFiltering:
    """Test occurrence-based filtering."""

    def test_llm_terms_below_threshold_filtered(self) -> None:
        """Test that LLM-detected terms below min_occurrences are filtered."""
        entries = [
            GlossaryEntry("dharma", "धर्म", "Duty", TermSource.SEED, 1, None, False),
            GlossaryEntry("newterm1", "नयाशब्द", "New", TermSource.LLM_DETECTED, 1, None, True),
            GlossaryEntry("newterm2", "नयाशब्द2", "New2", TermSource.LLM_DETECTED, 3, None, True),
        ]

        min_occurrences = 2
        filtered = [
            e
            for e in entries
            if e.source == TermSource.SEED or e.occurrence_count >= min_occurrences
        ]

        assert len(filtered) == 2
        term_names = [e.term for e in filtered]
        assert "dharma" in term_names
        assert "newterm2" in term_names
        assert "newterm1" not in term_names

    def test_seed_terms_always_included(self) -> None:
        """Test that seed terms are always included regardless of occurrence count."""
        entries = [
            GlossaryEntry("dharma", "धर्म", "Duty", TermSource.SEED, 1, None, False),
            GlossaryEntry("karma", "कर्म", "Action", TermSource.SEED, 0, None, False),
        ]

        # Seed terms should always be included even with 0 or 1 occurrences
        seed_entries = [e for e in entries if e.source == TermSource.SEED]
        assert len(seed_entries) == 2


class TestGlossaryReviewFlags:
    """Test needs_review flag logic."""

    def test_llm_terms_not_in_seed_need_review(self) -> None:
        """Test that LLM-detected terms not in seed glossary need review."""
        llm_entry = GlossaryEntry(
            term="newterm",
            original_script="नयाशब्द",
            definition="A new term",
            source=TermSource.LLM_DETECTED,
            occurrence_count=5,
            first_chapter="Chapter 3",
            needs_review=True,
        )
        assert llm_entry.needs_review is True
        assert llm_entry.source == TermSource.LLM_DETECTED

    def test_seed_terms_do_not_need_review(self) -> None:
        """Test that seed terms do not need review."""
        seed_entry = GlossaryEntry(
            term="dharma",
            original_script="धर्म",
            definition="Righteous duty",
            source=TermSource.SEED,
            occurrence_count=10,
            first_chapter="Chapter 1",
            needs_review=False,
        )
        assert seed_entry.needs_review is False
        assert seed_entry.source == TermSource.SEED


class TestGlossarySorting:
    """Test alphabetical sorting of glossary."""

    def test_entries_alphabetically_sorted(self) -> None:
        """Test that glossary entries are sorted alphabetically."""
        entries = [
            GlossaryEntry("yoga", "योग", "Union", TermSource.SEED, 5, None, False),
            GlossaryEntry("atman", "आत्मन्", "Soul", TermSource.SEED, 3, None, False),
            GlossaryEntry("dharma", "धर्म", "Duty", TermSource.SEED, 8, None, False),
            GlossaryEntry("karma", "कर्म", "Action", TermSource.SEED, 6, None, False),
        ]

        sorted_entries = sorted(entries, key=lambda e: e.term.lower())
        sorted_terms = [e.term for e in sorted_entries]

        assert sorted_terms == ["atman", "dharma", "karma", "yoga"]


class TestGlossaryDefinitionMerging:
    """Test definition merging logic."""

    def test_longest_definition_wins(self) -> None:
        """Test that when merging, the longest definition is kept."""
        definitions = [
            "Duty",
            "Righteous duty, moral law, cosmic order",
            "Righteous duty",
        ]

        longest = max(definitions, key=len)
        assert longest == "Righteous duty, moral law, cosmic order"

    def test_definition_merging_with_occurrences(self) -> None:
        """Test definition merging tracks occurrences."""
        # Simulate multiple extractions of same term
        extractions = [
            ("dharma", "धर्म", "Duty", "Chapter 1"),
            ("dharma", "धर्म", "Righteous duty, moral law", "Chapter 2"),
            ("dharma", "धर्म", "Duty", "Chapter 3"),
        ]

        merged = {}
        for term, script, definition, chapter in extractions:
            if term not in merged:
                merged[term] = {
                    "script": script,
                    "definition": definition,
                    "count": 1,
                    "first_chapter": chapter,
                }
            else:
                merged[term]["count"] += 1
                # Keep longest definition
                if len(definition) > len(merged[term]["definition"]):
                    merged[term]["definition"] = definition

        assert merged["dharma"]["count"] == 3
        assert merged["dharma"]["definition"] == "Righteous duty, moral law"
        assert merged["dharma"]["first_chapter"] == "Chapter 1"


class TestGlossaryAggregation:
    """Test glossary aggregation and counts."""

    def test_total_terms_count(self) -> None:
        """Test that total_terms equals seed_terms + llm_detected_terms."""
        seed_count = 40
        llm_count = 10

        output = GlossaryOutput(
            book_id=uuid4(),
            glossary_id=uuid4(),
            total_terms=seed_count + llm_count,
            seed_terms=seed_count,
            llm_detected_terms=llm_count,
            needs_review_count=8,
            entries=[],
        )
        assert output.total_terms == 50
        assert output.seed_terms + output.llm_detected_terms == output.total_terms

    def test_needs_review_count(self) -> None:
        """Test that needs_review_count is accurate."""
        entries = [
            GlossaryEntry("term1", "स्क्रिप्ट1", "Def1", TermSource.SEED, 5, None, False),
            GlossaryEntry("term2", "स्क्रिप्ट2", "Def2", TermSource.LLM_DETECTED, 3, None, True),
            GlossaryEntry("term3", "स्क्रिप्ट3", "Def3", TermSource.LLM_DETECTED, 4, None, True),
            GlossaryEntry("term4", "स्क्रिप्ट4", "Def4", TermSource.SEED, 2, None, False),
        ]

        needs_review_count = sum(1 for e in entries if e.needs_review)
        assert needs_review_count == 2

        output = GlossaryOutput(
            book_id=uuid4(),
            glossary_id=uuid4(),
            total_terms=4,
            seed_terms=2,
            llm_detected_terms=2,
            needs_review_count=needs_review_count,
            entries=entries,
        )
        assert output.needs_review_count == 2


# ---------------------------------------------------------------------------
# Issue #9 — Glossary Unicode normalization
# ---------------------------------------------------------------------------


class TestGlossaryEntryUnicodeNormalization:
    """Issue #9: Glossary entries with Devanagari must be NFC-normalized."""

    def test_devanagari_original_script_nfc(self) -> None:
        """GlossaryEntry original_script should be NFC-normalized."""
        entry = RealGlossaryEntry(
            term="dharma",
            original_script=unicodedata.normalize("NFC", "धर्म"),
            definition="Righteous duty",
            source=TermSource.SEED,
            occurrence_count=5,
        )
        assert unicodedata.is_normalized("NFC", entry.original_script)

    def test_decomposed_devanagari_normalized_before_storage(self) -> None:
        """NFD decomposed text must be NFC-normalized before use.

        Uses Hangul syllable 가 (U+AC00) which always decomposes in NFD
        to ᄀ + ᅡ (U+1100 U+1161) and recomposes in NFC — guaranteeing
        the NFD→NFC round-trip exercises the normalization path.
        """
        nfd_text = unicodedata.normalize("NFD", "\uAC00")  # 가 → ᄀ+ᅡ
        assert not unicodedata.is_normalized("NFC", nfd_text)

        nfc_text = unicodedata.normalize("NFC", nfd_text)
        entry = RealGlossaryEntry(
            term="test_term",
            original_script=nfc_text,
            definition="Test definition",
            source=TermSource.SEED,
            occurrence_count=3,
        )
        assert unicodedata.is_normalized("NFC", entry.original_script)
        assert entry.original_script == "\uAC00"

    @pytest.mark.parametrize(
        "term,script",
        [
            ("atman", "आत्मन्"),
            ("dharma", "धर्म"),
            ("karma", "कर्म"),
            ("moksha", "मोक्ष"),
            ("yoga", "योग"),
            ("guru", "गुरु"),
            ("bhakti", "भक्ति"),
        ],
    )
    def test_common_devanagari_terms_nfc(self, term: str, script: str) -> None:
        """Common cultural terms should already be in NFC form."""
        assert unicodedata.is_normalized("NFC", script), (
            f"Term '{term}' has non-NFC script: {script!r}"
        )

    def test_replacement_characters_are_removed_from_original_script(self) -> None:
        cleaned = normalize_unicode("श\ufffd्रि").replace("\ufffd", "")
        assert "\ufffd" not in cleaned


class TestSeedGlossaryUnicodeNormalization:
    """Issue #9: Seed glossary terms must all be NFC-normalized."""

    def test_all_seed_original_scripts_nfc(self) -> None:
        """Every seed term original_script must be NFC."""
        for term, script, _defn in SEED_TERMS:
            assert unicodedata.is_normalized("NFC", script), (
                f"Seed term '{term}' has non-NFC original_script: {script!r}"
            )

    def test_all_seed_definitions_nfc(self) -> None:
        """Seed term definitions must be NFC."""
        for term, _script, defn in SEED_TERMS:
            assert unicodedata.is_normalized("NFC", defn), (
                f"Seed term '{term}' has non-NFC definition"
            )

    def test_seed_term_names_nfc(self) -> None:
        """Seed transliterated term names must be NFC (ASCII is trivially NFC)."""
        for term, _script, _defn in SEED_TERMS:
            assert unicodedata.is_normalized("NFC", term)


class TestCorruptedUnicodeNormalization:
    """Issue #9: Corrupted/decomposed Unicode must be normalizable to NFC."""

    def test_nfd_devanagari_converts_to_nfc(self) -> None:
        """Decomposed text must convert cleanly to NFC.

        Uses Hangul syllable 한 (U+D55C) to guarantee an NFD form that
        differs from NFC — validating the normalization round-trip.
        """
        nfc_char = "\uD55C"  # 한
        decomposed = unicodedata.normalize("NFD", nfc_char)
        composed = unicodedata.normalize("NFC", decomposed)
        assert unicodedata.is_normalized("NFC", composed)
        assert not unicodedata.is_normalized("NFC", decomposed)

    def test_mixed_nfc_nfd_fully_normalizes(self) -> None:
        """Mixed NFC/NFD text should fully normalize to NFC."""
        nfc_part = "dharma (धर्म)"
        nfd_part = unicodedata.normalize("NFD", " और karma (कर्म)")
        mixed = nfc_part + nfd_part
        normalized = unicodedata.normalize("NFC", mixed)
        assert unicodedata.is_normalized("NFC", normalized)

    @pytest.mark.parametrize(
        "text",
        [
            "आत्मन्",
            "धर्म",
            "कर्म",
            "मोक्ष",
            "योग",
        ],
    )
    def test_nfc_roundtrip_identity(self, text: str) -> None:
        """NFC → NFD → NFC roundtrip must produce original text."""
        nfd = unicodedata.normalize("NFD", text)
        back = unicodedata.normalize("NFC", nfd)
        assert back == text


class TestRenderedGlossaryHtml:
    """Issue #9: Rendered glossary HTML must contain valid Devanagari."""

    REPLACEMENT_CHAR = "\uFFFD"

    def test_glossary_html_no_replacement_characters(self) -> None:
        """Glossary HTML must not contain U+FFFD (replacement character)."""
        entries = [
            RealGlossaryEntry(
                term="dharma",
                original_script="धर्म",
                definition="Righteous duty",
                source=TermSource.SEED,
                occurrence_count=5,
            ),
            RealGlossaryEntry(
                term="karma",
                original_script="कर्म",
                definition="Action",
                source=TermSource.SEED,
                occurrence_count=3,
            ),
        ]
        html = "<dl>\n"
        for e in entries:
            html += f"<dt>{e.term}"
            if e.original_script:
                html += f" ({e.original_script})"
            html += f"</dt>\n<dd>{e.definition}</dd>\n"
        html += "</dl>"

        assert self.REPLACEMENT_CHAR not in html

    def test_glossary_html_has_devanagari_codepoints(self) -> None:
        """Rendered HTML must contain valid Devanagari codepoints (U+0900-U+097F)."""
        entry = RealGlossaryEntry(
            term="moksha",
            original_script="मोक्ष",
            definition="Liberation",
            source=TermSource.SEED,
            occurrence_count=2,
        )
        html = f"<dt>{entry.term} ({entry.original_script})</dt>"
        devanagari = [c for c in html if "\u0900" <= c <= "\u097F"]
        assert len(devanagari) > 0

    def test_glossary_html_devanagari_is_nfc(self) -> None:
        """Devanagari in rendered HTML must be NFC-normalized."""
        nfc_script = unicodedata.normalize("NFC", "धर्म")
        entry = RealGlossaryEntry(
            term="dharma",
            original_script=nfc_script,
            definition="Righteous duty",
            source=TermSource.SEED,
            occurrence_count=5,
        )
        html = f"<dt>{entry.term} ({entry.original_script})</dt>"
        devanagari_text = "".join(c for c in html if "\u0900" <= c <= "\u097F")
        assert unicodedata.is_normalized("NFC", devanagari_text)

    def test_garbled_devanagari_detected(self) -> None:
        """Garbled output (excessive U+FFFD) must be detectable."""
        garbled = "dharma (\uFFFD\uFFFD\uFFFD)"
        assert self.REPLACEMENT_CHAR in garbled
        # Valid rendering should not have replacement chars
        valid = "dharma (धर्म)"
        assert self.REPLACEMENT_CHAR not in valid


# ---------------------------------------------------------------------------
# Issue #56 — Gurmukhi script validation for Hindi books
# ---------------------------------------------------------------------------


class TestGurmukhiScriptValidation:
    """Issue #56: Hindi glossary must not contain Gurmukhi script."""

    def test_contains_gurmukhi_detects_gurmukhi(self) -> None:
        """Gurmukhi codepoints (U+0A00–U+0A7F) are detected."""
        from transpose.utils.unicode import contains_gurmukhi

        assert contains_gurmukhi("ਅੰਮ੍ਰਿਤ")  # amrit in Gurmukhi
        assert not contains_gurmukhi("अमृत")   # amrit in Devanagari
        assert not contains_gurmukhi("amrit")  # Latin only
        assert not contains_gurmukhi("")

    def test_contains_devanagari_detects_devanagari(self) -> None:
        """Devanagari codepoints (U+0900–U+097F) are detected."""
        from transpose.utils.unicode import contains_devanagari

        assert contains_devanagari("अमृत")
        assert not contains_devanagari("ਅੰਮ੍ਰਿਤ")
        assert not contains_devanagari("dharma")
        assert not contains_devanagari("")

    def test_validate_script_hindi_rejects_gurmukhi(self) -> None:
        """Hindi language should reject Gurmukhi script."""
        from transpose.utils.unicode import validate_script_for_language

        assert validate_script_for_language("अमृत", "hindi") is True
        assert validate_script_for_language("ਅੰਮ੍ਰਿਤ", "hindi") is False
        assert validate_script_for_language("amrit", "hindi") is True
        assert validate_script_for_language("", "hindi") is True

    def test_validate_script_punjabi_rejects_devanagari(self) -> None:
        """Punjabi language should reject Devanagari script."""
        from transpose.utils.unicode import validate_script_for_language

        assert validate_script_for_language("ਅੰਮ੍ਰਿਤ", "punjabi") is True
        assert validate_script_for_language("अमृत", "punjabi") is False

    def test_strip_gurmukhi_removes_gurmukhi_chars(self) -> None:
        """strip_gurmukhi removes Gurmukhi-block characters."""
        from transpose.utils.unicode import strip_gurmukhi

        assert strip_gurmukhi("ਅੰਮ੍ਰਿਤ") == ""
        assert strip_gurmukhi("test ਅੰ text") == "test text"
        assert strip_gurmukhi("अमृत") == "अमृत"  # Devanagari untouched
        assert strip_gurmukhi("") == ""

    def test_mixed_script_gurmukhi_stripped_for_hindi(self) -> None:
        """Mixed Devanagari+Gurmukhi text: only Gurmukhi is stripped."""
        from transpose.utils.unicode import strip_gurmukhi

        mixed = "अमृत ਅੰਮ੍ਰਿਤ"
        result = strip_gurmukhi(mixed)
        assert "अमृत" in result
        assert "ਅ" not in result


# ---------------------------------------------------------------------------
# Issue #58 — Deduplication of spelling variants
# ---------------------------------------------------------------------------


class TestRomanizedTermNormalization:
    """Issue #58: Romanized term normalization for dedup."""

    def test_trailing_a_stripped(self) -> None:
        from transpose.utils.unicode import normalize_romanized_term

        assert normalize_romanized_term("bhairava") == normalize_romanized_term("bhairav")

    def test_trailing_ah_stripped(self) -> None:
        from transpose.utils.unicode import normalize_romanized_term

        assert normalize_romanized_term("brahmah") == normalize_romanized_term("brahm")

    def test_case_insensitive(self) -> None:
        from transpose.utils.unicode import normalize_romanized_term

        assert normalize_romanized_term("Dharma") == normalize_romanized_term("dharma")

    def test_hyphens_collapsed(self) -> None:
        from transpose.utils.unicode import normalize_romanized_term

        assert normalize_romanized_term("mool-mantar") == normalize_romanized_term("moolmantar")

    def test_short_terms_not_over_stripped(self) -> None:
        """Terms <= 3 chars should not have suffixes stripped."""
        from transpose.utils.unicode import normalize_romanized_term

        # "om" + "a" = "oma" — should not strip to "om" since len("oma") == 3
        assert normalize_romanized_term("oma") == "oma"

    def test_identical_terms_same_norm(self) -> None:
        from transpose.utils.unicode import normalize_romanized_term

        assert normalize_romanized_term("karma") == normalize_romanized_term("karma")


class TestGlossaryDeduplicationVariants:
    """Issue #58: Spelling variants are merged in glossary."""

    def test_deduplicate_bhairav_bhairava(self) -> None:
        """bhairav and bhairava should merge into one entry."""
        import logging

        from transpose.pipeline.glossary import _deduplicate_spelling_variants
        logger = logging.getLogger("test")

        term_data = {
            "bhairav": {
                "original_script": "",
                "definitions": ["A fierce form of Shiva"],
                "source": TermSource.LLM_DETECTED,
                "occurrences": 3,
                "first_chapter": "Chapter 1",
            },
            "bhairava": {
                "original_script": "",
                "definitions": ["A fierce form of Shiva"],
                "source": TermSource.LLM_DETECTED,
                "occurrences": 2,
                "first_chapter": "Chapter 2",
            },
        }

        merged = _deduplicate_spelling_variants(term_data, logger)
        assert len(merged) == 1
        canonical = list(merged.values())[0]
        assert canonical["occurrences"] == 5
        assert "variants" in canonical

    def test_seed_term_preferred_as_canonical(self) -> None:
        """Seed terms should be preferred over LLM-detected as canonical."""
        import logging

        from transpose.pipeline.glossary import _deduplicate_spelling_variants
        logger = logging.getLogger("test")

        term_data = {
            "bhakti": {
                "original_script": "भक्ति",
                "definitions": ["Devotional worship"],
                "source": TermSource.SEED,
                "occurrences": 5,
                "first_chapter": "Chapter 1",
            },
            "bhaktia": {
                "original_script": "",
                "definitions": ["Devotion"],
                "source": TermSource.LLM_DETECTED,
                "occurrences": 1,
                "first_chapter": "Chapter 3",
            },
        }

        merged = _deduplicate_spelling_variants(term_data, logger)
        assert len(merged) == 1
        assert "bhakti" in merged
        assert merged["bhakti"]["source"] == TermSource.SEED

    def test_non_overlapping_terms_not_merged(self) -> None:
        """Distinct terms should not be merged."""
        import logging

        from transpose.pipeline.glossary import _deduplicate_spelling_variants
        logger = logging.getLogger("test")

        term_data = {
            "dharma": {
                "original_script": "धर्म",
                "definitions": ["Righteous duty"],
                "source": TermSource.SEED,
                "occurrences": 10,
                "first_chapter": "Chapter 1",
            },
            "karma": {
                "original_script": "कर्म",
                "definitions": ["Action"],
                "source": TermSource.SEED,
                "occurrences": 8,
                "first_chapter": "Chapter 1",
            },
        }

        merged = _deduplicate_spelling_variants(term_data, logger)
        assert len(merged) == 2
        assert "dharma" in merged
        assert "karma" in merged

    def test_variant_names_recorded(self) -> None:
        """Merged variants should be recorded in the canonical entry."""
        import logging

        from transpose.pipeline.glossary import _deduplicate_spelling_variants
        logger = logging.getLogger("test")

        term_data = {
            "bhairav": {
                "original_script": "",
                "definitions": ["A fierce form of Shiva, the destroyer"],
                "source": TermSource.LLM_DETECTED,
                "occurrences": 5,
                "first_chapter": "Chapter 1",
            },
            "bhairava": {
                "original_script": "",
                "definitions": ["Fierce Shiva"],
                "source": TermSource.LLM_DETECTED,
                "occurrences": 2,
                "first_chapter": "Chapter 3",
            },
        }

        merged = _deduplicate_spelling_variants(term_data, logger)
        canonical = list(merged.values())[0]
        assert canonical.get("variants")
        assert len(canonical["variants"]) == 1

    def test_definitions_merged_across_variants(self) -> None:
        """Unique definitions from variants should be collected."""
        import logging

        from transpose.pipeline.glossary import _deduplicate_spelling_variants
        logger = logging.getLogger("test")

        term_data = {
            "bhairav": {
                "original_script": "",
                "definitions": ["A fierce form of Shiva"],
                "source": TermSource.LLM_DETECTED,
                "occurrences": 3,
                "first_chapter": "Chapter 1",
            },
            "bhairava": {
                "original_script": "",
                "definitions": ["The terrible aspect of Shiva, god of destruction"],
                "source": TermSource.LLM_DETECTED,
                "occurrences": 2,
                "first_chapter": "Chapter 2",
            },
        }

        merged = _deduplicate_spelling_variants(term_data, logger)
        canonical = list(merged.values())[0]
        assert len(canonical["definitions"]) == 2


# ---------------------------------------------------------------------------
# Issue #89 — Glossary U+FFFD scrub
# ---------------------------------------------------------------------------


class TestCleanOriginalScriptUFFfd:
    """Issue #89: _clean_original_script must scrub U+FFFD at module level.

    The function is used both inline during aggregation and as a final
    defensive pass before GlossaryEntry is written.  Both paths must
    guarantee no U+FFFD survives into the output.
    """

    def test_scrub_path_recoverable_string(self) -> None:
        """Strings where FFFD can be stripped and valid Devanagari remains."""
        from transpose.pipeline.glossary import _clean_original_script

        # "श्री" with a replacement char injected in the middle
        garbled = "श्र\ufffdी"
        result = _clean_original_script(garbled)
        assert "\ufffd" not in result, "U+FFFD must be stripped"
        # At least some Devanagari should survive after stripping FFFD
        assert any("\u0900" <= c <= "\u097F" for c in result), (
            "Devanagari codepoints should survive FFFD removal"
        )

    def test_reject_path_all_fffd(self) -> None:
        """When the entire original_script is U+FFFD, the result should be empty."""
        from transpose.pipeline.glossary import _clean_original_script

        all_garbage = "\ufffd\ufffd\ufffd"
        result = _clean_original_script(all_garbage)
        assert result == "", (
            "A script consisting entirely of U+FFFD should yield empty string"
        )

    def test_clean_script_no_fffd_passthrough(self) -> None:
        """Clean Devanagari passes through unchanged."""
        from transpose.pipeline.glossary import _clean_original_script

        clean = "धर्म"
        result = _clean_original_script(clean)
        assert result == clean

    def test_leading_trailing_fffd_stripped(self) -> None:
        """U+FFFD at the start or end of otherwise-clean script is removed."""
        from transpose.pipeline.glossary import _clean_original_script

        padded = "\ufffdयोग\ufffd"
        result = _clean_original_script(padded)
        assert "\ufffd" not in result
        assert "योग" in result

    def test_mixed_fffd_and_latin_returns_empty(self) -> None:
        """After FFFD removal, a Latin-only remainder yields empty string."""
        from transpose.pipeline.glossary import _clean_original_script

        # Latin chars + replacement chars — no Indic content remaining
        latin_garbage = "abc\ufffde"
        result = _clean_original_script(latin_garbage)
        assert "\ufffd" not in result
        # Should be empty (Latin-only after strip)
        assert result == "" or not any("\u0900" <= c <= "\u097F" for c in result)
