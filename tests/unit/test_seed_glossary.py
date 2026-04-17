"""Tests for the seed glossary."""

from transpose.config.seed_glossary import SEED_TERMS, get_seed_glossary


class TestSeedGlossary:
    def test_seed_terms_not_empty(self) -> None:
        assert len(SEED_TERMS) > 50

    def test_get_seed_glossary_returns_dict(self) -> None:
        glossary = get_seed_glossary()
        assert isinstance(glossary, dict)
        assert "dharma" in glossary
        assert "karma" in glossary
        assert "sangat" in glossary

    def test_seed_entries_have_all_fields(self) -> None:
        for term, script, definition in SEED_TERMS:
            assert term, "Term must not be empty"
            assert script, f"Script missing for {term}"
            assert definition, f"Definition missing for {term}"

    def test_no_duplicate_terms(self) -> None:
        terms = [t[0] for t in SEED_TERMS]
        assert len(terms) == len(set(terms)), "Duplicate terms found in seed glossary"
