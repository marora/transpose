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
    """
    import logging
    from collections import defaultdict

    from transpose.config.seed_glossary import get_seed_glossary
    from transpose.models.enums import TermSource
    from transpose.models.glossary import Glossary
    from transpose.models.translation import CulturalTerm
    from transpose.utils.unicode import normalize_unicode

    logger = logging.getLogger(__name__)

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
            if extracted_term.original_script and not data["original_script"]:
                data["original_script"] = normalize_unicode(extracted_term.original_script)
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

