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

## Quality Gates (`pipeline/gates.py`)

Quality gates are **blocking checks** between pipeline stages. Each gate validates the output of the previous stage before the next stage is allowed to run. If a gate fails, the pipeline halts with a `QualityGateError`.

### Gate Result Contract

```python
@dataclass
class GateResult:
    """Outcome of a single quality gate check."""
    gate_name: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
    timestamp: str  # UTC ISO 8601


class QualityGateError(Exception):
    """Raised when a quality gate fails, blocking pipeline progression."""
    gate_result: GateResult
```

### Gate 1: OCR Sanity

**Runs after:** OCR → before Chunk

```python
def ocr_sanity_gate(ocr_output: OcrOutput) -> GateResult:
```

| Check | Threshold | Description |
|-------|-----------|-------------|
| Garbled Unicode | U+FFFD ratio ≤ 5% per page | Detects corrupt OCR output |
| Devanagari density | ≥ 5% of non-space chars | Confirms Hindi source text was actually extracted |
| OCR confidence | ≥ 0.6 per page | Rejects pages with unreadable scans |

### Gate 2: Translation Completeness

**Runs after:** Translate → before Glossary

```python
def translation_completeness_gate(translate_output: TranslateOutput) -> GateResult:
```

| Check | Threshold | Description |
|-------|-----------|-------------|
| Failed chunk ratio | ≤ 10% | Ensures most chunks translated successfully |
| TRANSLATION FAILED markers | ≤ 10% of chunks | Catches LLM placeholder failures |
| Devanagari passthrough | ≤ 30% Devanagari in translated text | Detects untranslated source text leak |

### Gate 3: Glossary Integrity

**Runs after:** Glossary → before Assemble

```python
def glossary_integrity_gate(glossary_output: GlossaryOutput) -> GateResult:
```

| Check | Description |
|-------|-------------|
| Non-empty glossary | At least one entry required |
| NFC normalization | `original_script` fields must be NFC-normalized |
| No U+FFFD | No replacement characters in term, original_script, or definition |
| No Latin in Devanagari | No Latin characters mixed into `original_script` fields |

### Gate 4: Document Structure

**Runs after:** Assemble → before Export

```python
def document_structure_gate(manuscript: Manuscript) -> GateResult:
```

| Check | Threshold | Description |
|-------|-----------|-------------|
| ToC vs chapter count | Must match | Table of contents entries match actual chapters |
| Foreword present | ≥ 50 words | Translator's Foreword exists and is substantive |
| Title text | Non-empty | Manuscript has a title |
| Sequential chapters | 1, 2, 3, ... | Chapter numbers are sequential |

### Gate 5: Artifact Availability

**Runs after:** Export

```python
def artifact_availability_gate(export_output: ExportOutput) -> GateResult:
```

| Check | Threshold | Description |
|-------|-----------|-------------|
| PDF present | > 1 KB | PDF artifact exists and is non-trivial |
| ePub present | > 1 KB | ePub artifact exists and is non-trivial |
| Valid URIs | http/https/file/absolute path verified | Artifact URIs resolve to real files |

### Gate 6: Golden-Targeted QA

**Runs after:** Export (compares rendered PDF against `tests/golden/golden-target.json`)

```python
def golden_targeted_qa_gate(
    candidate_pdf_path: str,
    golden_target_path: str = "tests/golden/golden-target.json",
) -> GateResult:
```

| Check | Threshold | Description |
|-------|-----------|-------------|
| Structural match | Chapter count matches golden | Chapters present, sequential, required sections (cover, ToC, foreword, glossary) |
| Content completeness | Per-chapter word counts ±30% | Catches content bleed, truncation, or inflation |
| Script hygiene | < 2% Devanagari in body | No untranslated text in English body (glossary excluded) |
| Glossary integrity | Required terms present, min entry count | Key cultural terms appear in output |
| No regression | Page count ≤ 1.5× source | Prevents page-count inflation |

The golden target file itself is validated before use (no U+FFFD, chapters present with titles/word counts, cover and ToC sections).

### Gate 7: Production Readiness

**Runs after:** Export (inspects rendered PDF for visual/structural defects)

```python
def validate_production_readiness(
    candidate_pdf_path: str,
    golden_target_path: str = "tests/golden/golden-target.json",
) -> GateResult:
```

| Check | Description |
|-------|-------------|
| Devanagari rendering integrity | No IPA Extension chars (U+0250–02AF) in glossary, no digit substitutions in Devanagari words, known terms match expected Unicode sequences |
| ToC verification | Page numbers present, > 0, not all identical, monotonically increasing |
| Content completeness | Per-chapter word counts match golden target (with tolerance) |
| Cover validation | First page has meaningful title text |
| Structural integrity | Chapters present, ordered, no empty pages |

---

## Contract Rules

1. **Every stage function has the signature:** `async def run(input: StageInput) -> StageOutput`
2. **Stages never import each other.** The runner orchestrates.
3. **Stages communicate only through the database and their input/output contracts.**
4. **All IDs are UUIDs.** No sequential IDs.
5. **All timestamps are UTC.**
6. **Stages are idempotent.** Re-running with the same input produces the same output (or skips already-done work).
7. **Quality gates block stage transitions.** A gate failure halts the pipeline — the next stage does not run.
