"""Stage 5: Glossary — Cultural term aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from transpose.models.enums import TermSource


@dataclass
class GlossaryInput:
    book_id: UUID
    min_occurrences_for_llm_terms: int = 2


@dataclass
class GlossaryEntry:
    term: str
    original_script: str
    definition: str
    source: TermSource
    occurrence_count: int
    first_chapter: str | None = None
    needs_review: bool = False


@dataclass
class GlossaryOutput:
    book_id: UUID
    glossary_id: UUID
    total_terms: int
    seed_terms: int
    llm_detected_terms: int
    needs_review_count: int
    entries: list[GlossaryEntry] = field(default_factory=list)


async def run(input: GlossaryInput, ctx) -> GlossaryOutput:  # type: ignore[no-untyped-def]
    """Aggregate cultural terms from all translations into a glossary.

    Deduplicates, normalizes, merges definitions, counts occurrences.
    LLM-detected terms with < min_occurrences are filtered.
    Validates script correctness (Issue #56) and deduplicates spelling
    variants like bhairav/bhairava (Issue #58) before final assembly.
    """
    import logging
    from collections import defaultdict

    from transpose.config.seed_glossary import get_seed_glossary
    from transpose.models.enums import TermSource
    from transpose.models.glossary import Glossary
    from transpose.models.translation import CulturalTerm
    from transpose.utils.unicode import (
        contains_gurmukhi,
        is_latin_only,
        normalize_unicode,
        strip_gurmukhi,
        strip_latin_from_indic,
        validate_script_for_language,
    )

    logger = logging.getLogger(__name__)

    # Get book metadata for language-aware script validation
    book = await ctx.db.get_book(input.book_id)
    source_language = book.source_language.value if book else "hindi"

    # Get all translations
    translations = await ctx.db.get_translations_for_book(input.book_id)
    if not translations:
        raise ValueError(f"No translations found for book: {input.book_id}")

    logger.info(f"Processing {len(translations)} translations")

    # Get chunks to map chapter references
    chunks = await ctx.db.get_chunks_for_book(input.book_id)
    chunk_map = {chunk.id: chunk for chunk in chunks}

    # Aggregate terms by normalized form
    term_data: dict[str, dict] = defaultdict(
        lambda: {
            "original_script": "",
            "definitions": [],
            "source": None,
            "occurrences": 0,
            "first_chapter": None,
        }
    )

    seed_terms = get_seed_glossary()

    for translation in translations:
        chunk = chunk_map.get(translation.chunk_id)
        chapter_ref = chunk.chapter_ref if chunk else None

        for extracted_term in translation.cultural_terms:
            term_key = extracted_term.term.lower().strip()

            # Update aggregated data
            data = term_data[term_key]
            data["occurrences"] += 1

            # Keep original script (prefer non-empty), NFC-normalize Indic text.
            # Seed glossary entries have curated scripts — always prefer them
            # over LLM-detected forms which may be wrong (e.g. sangat).
            # Clear Latin-only original_script (e.g. "meditation") — the field
            # is for Indic script only; English loanwords don't belong here.
            # Strip stray Latin chars from mixed scripts (e.g. "L यान" → "यान").
            if extracted_term.original_script and not data["original_script"]:
                script = normalize_unicode(extracted_term.original_script)
                script = "" if is_latin_only(script) else strip_latin_from_indic(script)
                if script:
                    data["original_script"] = script
            if term_key in seed_terms and seed_terms[term_key][0]:
                data["original_script"] = normalize_unicode(seed_terms[term_key][0])

            # Collect definitions
            if extracted_term.definition and extracted_term.definition not in data["definitions"]:
                data["definitions"].append(extracted_term.definition)

            # Track source (seed takes precedence)
            if extracted_term.source == TermSource.SEED:
                data["source"] = TermSource.SEED
            elif data["source"] is None:
                data["source"] = TermSource.LLM_DETECTED

            # Track first chapter
            if data["first_chapter"] is None and chapter_ref:
                data["first_chapter"] = chapter_ref

    # ── Issue #56: Script validation ─────────────────────────────────
    # For Hindi books, strip Gurmukhi script from original_script fields.
    # The LLM sometimes returns Gurmukhi (ਅੰਮ੍ਰਿਤ) instead of Devanagari
    # (अमृत) for terms that exist in both traditions.
    gurmukhi_fixed = 0
    for term, data in term_data.items():
        script = data["original_script"]
        is_wrong_script = (
            script
            and not validate_script_for_language(script, source_language)
            and source_language in ("hindi", "hi")
            and contains_gurmukhi(script)
        )
        if is_wrong_script:
            cleaned = strip_gurmukhi(script)
            if cleaned:
                data["original_script"] = cleaned
            else:
                # Entirely Gurmukhi — clear the field so it doesn't
                # render wrong script in the glossary
                data["original_script"] = ""
            gurmukhi_fixed += 1
            logger.warning(
                "Script mismatch for '%s': stripped Gurmukhi from original_script "
                "(book language=%s)",
                term, source_language,
            )

    if gurmukhi_fixed:
        logger.info(
            "Issue #56: fixed %d glossary entries with wrong script", gurmukhi_fixed,
        )

    # ── Issue #58: Fuzzy deduplication of spelling variants ──────────
    # Group entries by their normalized romanized form so that
    # "bhairav" and "bhairava" collapse into one entry.
    term_data = _deduplicate_spelling_variants(term_data, logger)

    # Build glossary entries
    entries: list[GlossaryEntry] = []
    seed_count = 0
    llm_count = 0
    needs_review_count = 0

    for term, data in sorted(term_data.items()):
        # Filter LLM-detected terms with low occurrence
        if (
            data["source"] == TermSource.LLM_DETECTED
            and data["occurrences"] < input.min_occurrences_for_llm_terms
        ):
            continue

        # Merge definitions (use longest or most descriptive)
        definition = max(data["definitions"], key=len) if data["definitions"] else ""

        # Append "Also: variant1, variant2" when variants were merged
        variants = data.get("variants")
        if variants:
            variant_note = "Also: " + ", ".join(sorted(variants))
            if variant_note not in definition:
                definition = definition.rstrip(".") + ". " + variant_note

        # Flag LLM-detected terms not in seed for review
        needs_review = data["source"] == TermSource.LLM_DETECTED and term not in seed_terms

        entry = GlossaryEntry(
            term=term,
            original_script=data["original_script"],
            definition=definition,
            source=data["source"],
            occurrence_count=data["occurrences"],
            first_chapter=data["first_chapter"],
            needs_review=needs_review,
        )
        entries.append(entry)

        # Count by source
        if data["source"] == TermSource.SEED:
            seed_count += 1
        else:
            llm_count += 1

        if needs_review:
            needs_review_count += 1

        # Also save as CulturalTerm in DB for future reference
        cultural_term = CulturalTerm(
            book_id=input.book_id,
            term=term,
            definition=definition,
            original_script=data["original_script"],
            source=data["source"],
            occurrence_count=data["occurrences"],
            first_chapter=data["first_chapter"],
            needs_review=needs_review,
        )
        await ctx.db.upsert_cultural_term(cultural_term)

    # Create glossary record
    glossary = Glossary(
        book_id=input.book_id,
        entries=entries,
    )

    await ctx.db.create_glossary(glossary)

    logger.info(
        f"Created glossary with {len(entries)} terms "
        f"({seed_count} seed, {llm_count} LLM-detected, {needs_review_count} need review)"
    )

    # Build output
    output_entries = [
        GlossaryEntry(
            term=entry.term,
            original_script=entry.original_script,
            definition=entry.definition,
            source=entry.source,
            occurrence_count=entry.occurrence_count,
            first_chapter=entry.first_chapter,
            needs_review=entry.needs_review,
        )
        for entry in entries
    ]

    return GlossaryOutput(
        book_id=input.book_id,
        glossary_id=glossary.id,
        total_terms=len(entries),
        seed_terms=seed_count,
        llm_detected_terms=llm_count,
        needs_review_count=needs_review_count,
        entries=output_entries,
    )


def _deduplicate_spelling_variants(
    term_data: dict[str, dict],
    logger,
) -> dict[str, dict]:
    """Merge glossary entries that are spelling variants of the same term.

    Groups by ``normalize_romanized_term()`` (strips trailing vowels,
    lowercases, removes hyphens).  For each group the *canonical* entry
    is chosen as the one with the longest definition and highest occurrence
    count.  Other spellings are recorded in a ``"variants"`` set.
    """
    from collections import defaultdict

    from transpose.utils.unicode import normalize_romanized_term

    # bucket → list of (original_term, data)
    buckets: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for term, data in term_data.items():
        key = normalize_romanized_term(term)
        buckets[key].append((term, data))

    merged: dict[str, dict] = {}
    dedup_count = 0

    for _norm_key, group in buckets.items():
        if len(group) == 1:
            term, data = group[0]
            merged[term] = data
            continue

        # Pick canonical entry: prefer seed terms, then longest definition,
        # then highest occurrence count, then shortest spelling (more common).
        from transpose.models.enums import TermSource

        def _sort_key(pair: tuple[str, dict]) -> tuple:
            t, d = pair
            is_seed = 1 if d["source"] == TermSource.SEED else 0
            best_def_len = max((len(df) for df in d["definitions"]), default=0)
            return (is_seed, best_def_len, d["occurrences"], -len(t))

        group_sorted = sorted(group, key=_sort_key, reverse=True)
        canonical_term, canonical_data = group_sorted[0]

        # Merge others into canonical
        variant_names: set[str] = set()
        for other_term, other_data in group_sorted[1:]:
            variant_names.add(other_term)
            canonical_data["occurrences"] += other_data["occurrences"]
            for defn in other_data["definitions"]:
                if defn not in canonical_data["definitions"]:
                    canonical_data["definitions"].append(defn)
            if not canonical_data["original_script"] and other_data["original_script"]:
                canonical_data["original_script"] = other_data["original_script"]
            if not canonical_data["first_chapter"] and other_data["first_chapter"]:
                canonical_data["first_chapter"] = other_data["first_chapter"]
            # Seed source wins
            if other_data["source"] == TermSource.SEED:
                canonical_data["source"] = TermSource.SEED

        canonical_data["variants"] = variant_names
        merged[canonical_term] = canonical_data
        dedup_count += len(variant_names)

        logger.info(
            "Issue #58: merged variants %s → '%s'",
            sorted(variant_names), canonical_term,
        )

    if dedup_count:
        logger.info(
            "Issue #58: deduplicated %d spelling variant(s)", dedup_count,
        )

    return merged

