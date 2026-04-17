# Transpose — API Contracts

> Defines the input/output contract for each pipeline stage.
> These are the boundaries. Respect them.

---

## Common Types

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class BookStatus(str, Enum):
    INGESTED = "ingested"
    OCR_COMPLETE = "ocr_complete"
    CHUNKED = "chunked"
    TRANSLATED = "translated"
    ASSEMBLED = "assembled"
    EXPORTED = "exported"
    FAILED = "failed"


class SourceLanguage(str, Enum):
    HINDI = "hindi"
    PUNJABI = "punjabi"


class SectionType(str, Enum):
    CHAPTER = "chapter"
    HEADING = "heading"
    VERSE = "verse"
    PROSE = "prose"


class TermSource(str, Enum):
    SEED = "seed"
    LLM_DETECTED = "llm_detected"
```

---

## Stage 1: Ingest

```python
@dataclass
class IngestInput:
    """What the ingest stage receives."""
    source_path: str          # Local file path or Azure Blob URI
    title: str                # Book title
    author: str | None = None
    source_language: SourceLanguage = SourceLanguage.HINDI


@dataclass
class IngestOutput:
    """What the ingest stage produces."""
    book_id: UUID
    source_hash: str
    source_blob_uri: str
    page_count: int
    already_existed: bool     # True if this PDF was already ingested (dedup)
```

---

## Stage 2: OCR

```python
@dataclass
class OcrInput:
    """What the OCR stage receives."""
    book_id: UUID


@dataclass
class PageResult:
    """OCR result for a single page."""
    page_number: int
    raw_text: str
    confidence: float
    needs_review: bool
    ocr_metadata: dict        # Bounding boxes, reading order, etc.


@dataclass
class OcrOutput:
    """What the OCR stage produces."""
    book_id: UUID
    pages_processed: int
    pages_skipped: int        # Already processed in a previous run
    low_confidence_count: int
    page_results: list[PageResult]
```

---

## Stage 3: Chunk

```python
@dataclass
class ChunkInput:
    """What the chunk stage receives."""
    book_id: UUID
    target_chunk_tokens: int = 1500
    overlap_tokens: int = 150


@dataclass
class ChunkResult:
    """A single chunk produced by the chunking stage."""
    chunk_id: UUID
    sequence: int
    source_text: str
    token_count: int
    chapter_ref: str | None
    section_type: SectionType
    page_start: int
    page_end: int


@dataclass
class ChunkOutput:
    """What the chunk stage produces."""
    book_id: UUID
    total_chunks: int
    chunks: list[ChunkResult]
```

---

## Stage 4: Translate

```python
@dataclass
class TranslateInput:
    """What the translate stage receives."""
    book_id: UUID
    force_retranslate: bool = False  # Re-translate already translated chunks
    concurrency: int = 5             # Max parallel translation calls


@dataclass
class ExtractedTerm:
    """A cultural term extracted during translation."""
    term: str                 # Transliterated form (e.g., "dharma")
    original_script: str      # Original script (Devanagari/Gurmukhi)
    definition: str           # Brief English gloss
    source: TermSource


@dataclass
class TranslationResult:
    """Translation result for a single chunk."""
    chunk_id: UUID
    translated_text: str
    cultural_terms: list[ExtractedTerm]
    prompt_tokens: int
    completion_tokens: int
    model_version: str


@dataclass
class TranslateOutput:
    """What the translate stage produces."""
    book_id: UUID
    chunks_translated: int
    chunks_skipped: int       # Already translated (unless force_retranslate)
    total_prompt_tokens: int
    total_completion_tokens: int
    cultural_terms_found: int
    translations: list[TranslationResult]
```

---

## Stage 5: Glossary

```python
@dataclass
class GlossaryInput:
    """What the glossary stage receives."""
    book_id: UUID
    min_occurrences_for_llm_terms: int = 2  # LLM-detected terms need 2+ occurrences


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
    """What the glossary stage produces."""
    book_id: UUID
    glossary_id: UUID
    total_terms: int
    seed_terms: int
    llm_detected_terms: int
    needs_review_count: int
    entries: list[GlossaryEntry]
```

---

## Stage 6: Assemble

```python
@dataclass
class AssembleInput:
    """What the assemble stage receives."""
    book_id: UUID
    glossary_position: str = "back"  # "front" or "back" matter


@dataclass
class Chapter:
    """A chapter in the assembled manuscript."""
    number: int
    title: str
    content_html: str         # Semantic HTML content


@dataclass
class AssembleOutput:
    """What the assemble stage produces."""
    book_id: UUID
    manuscript_id: UUID
    title: str
    author: str | None
    chapters: list[Chapter]
    glossary_id: UUID
    table_of_contents: list[dict]  # [{chapter: int, title: str}]
```

---

## Stage 7: Export

```python
@dataclass
class ExportInput:
    """What the export stage receives."""
    book_id: UUID
    formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])


@dataclass
class ExportArtifact:
    """A single exported file."""
    format: str               # "epub" or "pdf"
    blob_uri: str             # Azure Blob URI
    file_size_bytes: int


@dataclass
class ExportOutput:
    """What the export stage produces."""
    book_id: UUID
    artifacts: list[ExportArtifact]
```

---

## Pipeline Runner Contract

```python
@dataclass
class PipelineInput:
    """Top-level input to run the full pipeline."""
    source_path: str
    title: str
    author: str | None = None
    source_language: SourceLanguage = SourceLanguage.HINDI
    output_formats: list[str] = field(default_factory=lambda: ["epub", "pdf"])
    resume_from: str | None = None  # Stage name to resume from (if restarting)


@dataclass
class PipelineOutput:
    """Top-level output of the full pipeline."""
    book_id: UUID
    status: BookStatus
    artifacts: list[ExportArtifact]
    glossary_term_count: int
    total_tokens_used: int
    stages_completed: list[str]
    errors: list[dict]        # Any non-fatal errors encountered
```

---

## Contract Rules

1. **Every stage function has the signature:** `async def run(input: StageInput) -> StageOutput`
2. **Stages never import each other.** The runner orchestrates.
3. **Stages communicate only through the database and their input/output contracts.**
4. **All IDs are UUIDs.** No sequential IDs.
5. **All timestamps are UTC.**
6. **Stages are idempotent.** Re-running with the same input produces the same output (or skips already-done work).
