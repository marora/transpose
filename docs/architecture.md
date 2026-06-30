# Transpose — Architecture

> Agentic pipeline for translating scanned/digital PDF books from Hindi/Punjabi into English.
> Preserves culturally significant terms. Produces publication-ready ePub/PDF.

**Decision owner:** Stilgar (Lead/Architect)
**Status:** Active — Phase 1 (end-to-end pipeline)

---

## System Overview

Transpose is a **staged pipeline** — each stage is an independent module with defined inputs, outputs, and failure semantics. Stages communicate through a shared PostgreSQL state store. Pipeline orchestration state (progress tracking, distributed locks) is also in PostgreSQL.

The pipeline is **idempotent and resumable**. Any stage can be re-run from its last checkpoint without corrupting state. This is non-negotiable — books are large, LLM calls are expensive, and failures will happen.

### Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRANSPOSE PIPELINE                              │
│                                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │          │   │          │   │          │   │          │            │
│  │  INGEST  ├──►│   OCR    ├──►│ CHUNK    ├──►│TRANSLATE │            │
│  │          │   │          │   │          │   │          │            │
│  └──────────┘   └──────────┘   └──────────┘   └────┬─────┘            │
│                                                     │                   │
│                                    ┌────────────────┤                   │
│                                    │                │                   │
│                                    ▼                ▼                   │
│                              ┌──────────┐   ┌──────────┐              │
│                              │          │   │          │              │
│                              │ GLOSSARY │   │ ASSEMBLE │              │
│                              │          │   │          │              │
│                              └──────────┘   └────┬─────┘              │
│                                                   │                    │
│                                                   ▼                    │
│                                            ┌──────────┐               │
│                                            │          │               │
│                                            │  EXPORT  │               │
│                                            │          │               │
│                                            └──────────┘               │
│                                                                        │
└─────────────────────────────────────────────────────────────────────────┘

State: PostgreSQL                                       Observability: App Insights
```

---

## Pipeline Stages

### Stage 1: Ingest

**Purpose:** Accept a PDF (scanned or digital), validate it, register the book in the system, and store the source file.

| Property | Value |
|----------|-------|
| **Input** | PDF file path or Azure Blob URI |
| **Output** | `Book` record in DB, source PDF stored in blob |
| **Idempotent** | Yes — re-ingest of same file is a no-op (content hash dedup) |
| **Azure Services** | Blob Storage |

**Behavior:**
- Compute SHA-256 of the source PDF
- If hash exists in DB, return existing book record
- Detect source language (Hindi/Punjabi) from metadata or first-page OCR sample
- Store original PDF in Azure Blob Storage
- Create `Book` record with status `ingested`

### Stage 2: OCR

**Purpose:** Extract text from scanned pages using Azure AI Document Intelligence. Digital PDFs skip heavy OCR and use lightweight text extraction.

| Property | Value |
|----------|-------|
| **Input** | `Book` record (status: `ingested`) |
| **Output** | `Page` records with extracted text, reading order, and confidence scores |
| **Idempotent** | Yes — pages already processed are skipped |
| **Azure Services** | AI Document Intelligence (prebuilt-read model) |

**Behavior:**
- Detect if PDF is scanned (image-based) or digital (text-layer present)
- For scanned: use Document Intelligence `prebuilt-read` layout model
- For digital: extract text directly via PDF parser (PyMuPDF), fall back to Document Intelligence if extraction quality is low
- Store per-page results: text content, bounding boxes (for future layout preservation), reading order, confidence score
- Pages with confidence < 0.7 are flagged for review
- Process pages in parallel batches (configurable concurrency)

### Stage 3: Chunk

**Purpose:** Split OCR'd text into translation-ready chunks that respect semantic boundaries (paragraphs, sections, verses).

| Property | Value |
|----------|-------|
| **Input** | `Page` records for a book |
| **Output** | `Chunk` records — semantically coherent text units |
| **Idempotent** | Yes — re-chunking replaces existing chunks |

**Behavior:**
- Merge page text into a continuous document stream (respecting reading order)
- Split on structural boundaries: chapter breaks, section headers, paragraph breaks, verse markers
- Target chunk size: 1000-2000 tokens (tunable). This fits well within GPT-4o context while preserving enough context for quality translation
- Overlap: 100-200 tokens between chunks for translation continuity
- Tag chunks with structural metadata (chapter number, section type, position)
- Preserve original page references for downstream layout

### Stage 4: Translate

**Purpose:** Translate each chunk from source language to English using Azure OpenAI GPT-4o, preserving cultural terms.

| Property | Value |
|----------|-------|
| **Input** | `Chunk` records (source language text) |
| **Output** | `Translation` records (English text + extracted cultural terms) |
| **Idempotent** | Yes — chunks already translated are skipped unless force-retranslate |
| **Azure Services** | Azure OpenAI (GPT-4o) |

**Behavior:**
- System prompt instructs the model to:
  1. Translate literary Hindi/Punjabi to natural, publication-quality English
  2. Preserve culturally significant terms in their transliterated form (e.g., *atman*, *dharma*, *karma*, *sangat*, *langar*, *seva*)
  3. On first occurrence of a preserved term, provide a brief parenthetical gloss
  4. Return structured output: translated text + list of preserved terms with definitions
- Use JSON mode for structured response parsing
- Pass previous chunk's tail as context for translation continuity
- Retry with exponential backoff on rate limits (429) and transient errors (5xx)
- Store both the raw LLM response and parsed translation
- Track token usage per chunk for cost monitoring

**Cultural Term Detection Strategy:**
- Seed glossary: a curated list of ~200 known cultural/spiritual terms across Hindi and Punjabi traditions (Sikh, Hindu, Buddhist, Jain terminology)
- LLM-detected terms: the translation prompt asks GPT-4o to identify additional terms it chose to preserve
- Merge strategy: LLM-detected terms are added to the book's glossary if they appear 2+ times across chunks (filters noise)
- Human review flag: terms detected by LLM but not in the seed glossary are flagged for review

### Stage 5: Glossary

**Purpose:** Aggregate all preserved cultural terms across the book into a consolidated glossary.

| Property | Value |
|----------|-------|
| **Input** | All `Translation` records for a book |
| **Output** | `Glossary` — deduplicated, sorted, with definitions and occurrence counts |
| **Idempotent** | Yes — rebuilds from translation records |

**Behavior:**
- Collect all cultural terms from all translation records
- Deduplicate (normalize transliteration variants: e.g., "atma" / "atman")
- Merge definitions — pick the best gloss (longest, most descriptive)
- Count occurrences and record first-appearance chapter
- Sort alphabetically
- Flag terms needing human review (LLM-detected, not in seed glossary, low occurrence count)
- Output: structured glossary ready for front-matter/back-matter insertion

### Stage 6: Assemble

**Purpose:** Reassemble translated chunks into a structured document with chapters, sections, and metadata.

| Property | Value |
|----------|-------|
| **Input** | `Translation` records + `Glossary` + `Book` metadata |
| **Output** | `Manuscript` — ordered, structured document ready for formatting |
| **Idempotent** | Yes |

**Behavior:**
- Order translations by chunk sequence
- Reconstruct chapter/section structure from chunk metadata
- Insert glossary as back-matter (configurable: front or back)
- Apply translation continuity cleanup (fix cross-chunk sentence breaks)
- Generate table of contents from chapter structure
- Attach book metadata (title, author, translator credit, source language)

### Stage 7: Export

**Purpose:** Render the assembled manuscript into publication-ready ePub and PDF formats.

| Property | Value |
|----------|-------|
| **Input** | `Manuscript` |
| **Output** | ePub file, PDF file stored in Azure Blob |
| **Idempotent** | Yes — re-export overwrites |

**Behavior:**
- ePub generation: use `ebooklib` — semantic HTML chapters, CSS styling, embedded metadata, glossary as appendix
- PDF generation: use `weasyprint` — CSS-based PDF rendering from the same semantic HTML
- Both formats include: cover page, title page, table of contents, translated chapters, glossary, colophon
- Store outputs in Azure Blob Storage
- Update book status to `exported`

---

### Stage 8: Audiobook (optional)

**Purpose:** Generate a podcast-quality audiobook from the translated manuscript using neural TTS, with mastering, RSS distribution, and read-along transcripts.

| Property | Value |
|----------|-------|
| **Input** | `Manuscript`, glossary (for pronunciation lexicon) |
| **Output** | Mastered MP3 per chapter (Azure Blob), RSS feed XML, VTT/SRT transcripts, consumer listen page |
| **Idempotent** | Yes — re-run overwrites existing audio artifacts |
| **Opt-in** | Only runs when `audiobook` is in `output_formats` (`--format audiobook`) |

**Behavior:**
- Extract plain text from chapter HTML, split long chapters at paragraph boundaries (~25 min target)
- Build pronunciation lexicon from glossary (IPA for cultural terms: dharma, sangat, waheguru, etc.)
- Synthesize via configurable TTS provider (default: Azure Speech Neural HD) with SSML prosody:
  - Rate: -10%, paragraph pauses: 500ms, chapter intro pause: 2s
  - Chapter title spoken as intro
- **Mastering** (ffmpeg, two-pass):
  - EBU R128 loudness normalization to -16 LUFS (Spotify/podcast standard)
  - Dynamic range compression (threshold -20dB, ratio 3:1)
  - Silence trimming (max 300ms gaps)
  - Fade-in (100ms), 44.1kHz / 192kbps MP3 output
- Upload mastered MP3 + word boundary JSON to blob storage
- Generate Podcast 2.0 RSS feed (iTunes tags, `<podcast:transcript>` tags, enclosures)
- Generate VTT/SRT transcripts (paragraph-level from word boundaries)
- Serve consumer listen page with chapter navigation and share links

**Quality gate** (`audio_quality_gate`): validates after audiobook stage:
- At least one chapter audio produced
- All files > 1KB (not empty/corrupted)
- Duration: each chapter between 5s and 30 min
- Chapter completeness matches manuscript

**TTS provider abstraction:**
- `TTSProvider` ABC (`synthesize`, `get_available_voices`, `estimate_cost`, `supports_ssml`)
- Azure implementation: full SSML, word boundary events, HD Neural voices
- ElevenLabs / OpenAI: stubs for future swap (`TRANSPOSE_TTS_PROVIDER` config)

---

### Stage 9: Workspace

**Purpose:** Upload final artifacts, write metadata, publish per-book landing page to Azure Static Website.

| Property | Value |
|----------|-------|
| **Input** | All prior stage outputs |
| **Output** | Public landing page URL, metadata.json |
| **Non-fatal** | Warns and skips if static website URL not configured |

---

## Data Models

### Core Entities

```
Book
├── id: UUID
├── title: str
├── author: str | None
├── source_language: "hindi" | "punjabi"
├── source_hash: str (SHA-256)
├── source_blob_uri: str
├── status: BookStatus (ingested → ocr_complete → chunked → translated → assembled → exported)
├── page_count: int
├── created_at: datetime
└── updated_at: datetime

Page
├── id: UUID
├── book_id: UUID (FK → Book)
├── page_number: int
├── raw_text: str
├── confidence: float
├── needs_review: bool
├── ocr_metadata: dict (bounding boxes, reading order)
└── created_at: datetime

Chunk
├── id: UUID
├── book_id: UUID (FK → Book)
├── sequence: int (ordering)
├── source_text: str
├── token_count: int
├── chapter_ref: str | None
├── section_type: str (chapter, verse, prose, heading)
├── page_start: int
├── page_end: int
└── created_at: datetime

Translation
├── id: UUID
├── chunk_id: UUID (FK → Chunk)
├── book_id: UUID (FK → Book)
├── translated_text: str
├── cultural_terms: list[CulturalTerm]
├── model_version: str
├── prompt_tokens: int
├── completion_tokens: int
├── raw_response: dict
└── created_at: datetime

CulturalTerm
├── id: UUID
├── book_id: UUID (FK → Book)
├── term: str (transliterated)
├── original_script: str (Devanagari/Gurmukhi)
├── definition: str
├── source: "seed" | "llm_detected"
├── occurrence_count: int
├── first_chapter: str | None
├── needs_review: bool
└── created_at: datetime

Glossary
├── id: UUID
├── book_id: UUID (FK → Book)
├── terms: list[CulturalTerm] (ordered)
├── generated_at: datetime
└── version: int

Manuscript
├── id: UUID
├── book_id: UUID (FK → Book)
├── structure: dict (chapter tree with content refs)
├── metadata: dict (title, author, etc.)
├── glossary_id: UUID (FK → Glossary)
└── created_at: datetime
```

### Pipeline State (PostgreSQL)

Pipeline orchestration state is tracked in the `pipeline_state` table:

```sql
-- Pipeline state table (replaces former Redis keys)
CREATE TABLE pipeline_state (
    book_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    progress_completed INTEGER,
    progress_total INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- **Status tracking:** `pipeline_state.stage` / `pipeline_state.status` per book.
- **Progress within a stage:** `progress_completed` / `progress_total` columns.
- **Distributed locks:** PostgreSQL advisory locks (`pg_try_advisory_lock(hashtext(book_id))`).
- All state is durable — losing a process loses no progress.

---

## Database Schema (PostgreSQL)

```sql
-- Books table
CREATE TABLE books (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    author TEXT,
    source_language TEXT NOT NULL CHECK (source_language IN ('hindi', 'punjabi')),
    source_hash TEXT NOT NULL UNIQUE,
    source_blob_uri TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ingested',
    page_count INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Pages table
CREATE TABLE pages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    raw_text TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    ocr_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book_id, page_number)
);

-- Chunks table
CREATE TABLE chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,
    source_text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    chapter_ref TEXT,
    section_type TEXT NOT NULL DEFAULT 'prose',
    page_start INTEGER NOT NULL,
    page_end INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book_id, sequence)
);

-- Translations table
CREATE TABLE translations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    translated_text TEXT NOT NULL,
    model_version TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chunk_id)
);

-- Cultural terms table
CREATE TABLE cultural_terms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    term TEXT NOT NULL,
    original_script TEXT,
    definition TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('seed', 'llm_detected')),
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_chapter TEXT,
    needs_review BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (book_id, term)
);

-- Glossaries table
CREATE TABLE glossaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    version INTEGER NOT NULL DEFAULT 1,
    UNIQUE (book_id, version)
);

-- Manuscripts table
CREATE TABLE manuscripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    book_id UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    structure JSONB NOT NULL,
    metadata JSONB NOT NULL,
    glossary_id UUID REFERENCES glossaries(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX idx_pages_book_id ON pages(book_id);
CREATE INDEX idx_chunks_book_id ON chunks(book_id);
CREATE INDEX idx_translations_book_id ON translations(book_id);
CREATE INDEX idx_cultural_terms_book_id ON cultural_terms(book_id);
CREATE INDEX idx_books_status ON books(status);
```

---

## Azure Service Integration

| Service | Purpose | Auth | SDK |
|---------|---------|------|-----|
| **AI Document Intelligence** | OCR for scanned PDFs | Managed Identity | `azure-ai-documentintelligence` |
| **Azure OpenAI (GPT-4o)** | Literary translation | Managed Identity | `openai` (Azure endpoint) |
| **Azure Blob Storage** | Source PDFs + output files | Managed Identity | `azure-storage-blob` |
| **Azure Key Vault** | Non-identity secrets (if any) | Managed Identity | `azure-keyvault-secrets` |
| **Azure Container Apps** | Compute runtime | — | — |
| **Application Insights** | Traces, metrics, logs | Connection string | `azure-monitor-opentelemetry` |
| **PostgreSQL Flexible Server** | Persistent state | Managed Identity (Entra auth) | `asyncpg` |


**Auth principle:** Managed Identity everywhere. No connection strings or API keys in code or config. Key Vault only for third-party secrets or as a fallback.

---

## Error Handling & Retry Strategy

### Retry Policy

| Error Class | Strategy | Max Retries | Backoff |
|-------------|----------|-------------|---------|
| Azure OpenAI 429 (rate limit) | Exponential backoff + jitter | 5 | 2s, 4s, 8s, 16s, 32s |
| Azure OpenAI 5xx | Exponential backoff | 3 | 1s, 2s, 4s |
| Document Intelligence transient | Exponential backoff | 3 | 2s, 4s, 8s |
| Database connection | Reconnect with backoff | 5 | 1s, 2s, 4s, 8s, 16s |
| Blob Storage transient | SDK built-in retry | 3 | SDK default |

### Dead Letter Handling

- After max retries exhausted, the failed unit (page, chunk, translation) is marked `failed` in the database with the error details
- Pipeline continues processing other units — one bad page doesn't block the book
- Failed units can be retried manually or by re-running the stage
- A book can only advance to the next stage when all units in the current stage are `completed` or explicitly `skipped`

### Circuit Breaker

- If >30% of units in a batch fail, halt the stage and alert
- Prevents burning through API quota on systemic issues (bad prompt, service outage)

---

## Observability

### Traces

Every pipeline stage execution is a span. Child spans for individual API calls (OCR per page, translate per chunk). Distributed trace ID follows a book through the entire pipeline.

### Metrics

- `transpose.pipeline.stage_duration` — histogram per stage
- `transpose.pipeline.chunks_translated` — counter
- `transpose.openai.tokens_used` — counter (prompt + completion, per model)
- `transpose.translation.estimated_cost_usd` — counter (estimated cost based on token pricing)
- `transpose.ocr.pages_processed` — counter
- `transpose.ocr.low_confidence_pages` — counter
- `transpose.errors` — counter by stage and error type

### Structured Logging

All logs include: `book_id`, `stage`, `correlation_id`. JSON format. No PII in logs.

---

## Quality Gates (`pipeline/gates.py`)

Blocking checks that run between pipeline stages. If a gate fails, the pipeline halts with a `QualityGateError` — no stage runs until the previous gate passes. Gates are addressed by name (matching the function name in `pipeline/gates.py`) — code is the source of truth. There are **11 gates** in production.

| Gate | Stage | Checks |
|------|-------|--------|
| `operational_readiness_gate` | Preflight (before Stage 1: Ingest) | Azure / DB / model-endpoint reachability checks. Returns `OperationalReadinessResult`. Halts the run early if infrastructure dependencies are unavailable. |
| `ocr_sanity_gate` | After OCR (before Chunk) | Garbled Unicode (U+FFFD ratio), Devanagari codepoint density (≥5%), per-page confidence (≥0.6) |
| `translation_completeness_gate` | After Translate (before Glossary) | Every chunk has a translation, failed-chunk ratio ≤10%, no raw Devanagari passthrough (>30% threshold) |
| `glossary_integrity_gate` | After Glossary (before Assemble) | Non-empty glossary, NFC-normalized `original_script`, no U+FFFD in any field, no Latin chars in Devanagari fields |
| `document_structure_gate` | After Assemble (before Export) | ToC count matches chapter count, Translator's Foreword present (≥50 words), title text present, sequential chapter numbering |
| `artifact_availability_gate` | After Export | PDF and ePub both present and >1 KB, valid URIs (http/https/file/absolute paths verified) |
| `golden_targeted_qa_gate` | Post-export | Compares candidate PDF against `tests/golden/golden-target.json` — structural match (chapter count, sections), content completeness (per-chapter word counts ±30%), script hygiene (<2% Devanagari in body), glossary term presence, page-count regression (≤1.5× source). Validates the golden target file itself before trusting it as a reference. |
| `validate_production_readiness` | Post-export | Rendered output inspection — Devanagari rendering integrity (no IPA/digit substitutions), ToC page-number verification (present, monotonic, not all "1"), per-chapter word counts, cover-page validation, no empty pages |
| `export_rendering_gate` | Post-export (on produced PDF) | Verifies the exported PDF renders correctly: fonts embed, pages are countable, the document opens without errors |
| `source_output_comparison_gate` | Post-export (source vs. output) | Compares source PDF against translated PDF: page-count ratio (within `_STRUCTURAL_PAGE_RATIO_MIN` / `_STRUCTURAL_PAGE_RATIO_MAX`), text density, structural consistency |
| `audio_quality_gate` | After Audiobook | Chapter completeness (≥1 produced), file integrity (>1 KB), duration bounds (5s–30 min per chapter) |

Each gate returns a `GateResult` with `gate_name`, `passed`, `failures[]`, `details{}`, and a UTC timestamp (`operational_readiness_gate` returns the richer `OperationalReadinessResult`). All gate executions are wrapped in a `quality_gate` OTel span and emit the `gate_executions` / `gate_duration_seconds` metrics — see [observability.md](observability.md) for the telemetry contract. The aggregated per-run validation report shape is documented in [api-contracts.md](api-contracts.md).

---

## HTTP API (`api.py`)

Lightweight aiohttp-based API for triggering the pipeline remotely (designed for Azure Container Apps).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health probe — returns `{"status": "healthy"}` |
| `/translate` | POST | Accepts `{blob_uri, title, language?, author?, formats?}`, returns `{book_id, status: "accepted"}`, runs pipeline in background |
| `/status/{book_id}` | GET | Returns pipeline status (in-memory tracker first, falls back to DB) |
| `/audiobook/{book_id}` | GET | Audiobook metadata JSON (chapters, durations, feed URL) |
| `/audiobook/{book_id}/feed.xml` | GET | Podcast 2.0 RSS feed (subscribable in podcast apps) |
| `/audiobook/{book_id}/chapter/{n}` | GET | Redirect to chapter MP3 blob (SAS-signed URL) |
| `/audiobook/{book_id}/listen` | GET | Consumer HTML listen page with chapter player and share links |

---

## Service Context (`services/context.py`)

Dependency-injection container that holds all initialized service clients. Pipeline stages receive a `ctx: ServiceContext` parameter — they never construct clients directly.

Holds: `Database`, `PipelineState`, `BlobClient`, `OcrClient`, `LlmClient`, `TTSProvider`. Call `ctx.connect()` to initialize, `ctx.close()` to tear down.

---

## Unicode Normalization (`utils/unicode.py`)

`normalize_unicode(text)` applies NFC normalization at every layer boundary. Devanagari and Gurmukhi composed characters can arrive in multiple equivalent byte sequences (NFD vs NFC); NFC is the canonical form expected by fonts, search, and rendering engines.

---

## Cross-Page Paragraph Joining (`pipeline/chunk.py`)

The chunker detects paragraphs that span page boundaries. When a page ends without terminal punctuation (`.`, `?`, `!`, `।`, `॥`) and the next page starts with a continuation pattern (lowercase letter or Devanagari character), the artificial page break is replaced with a single space so the downstream paragraph splitter keeps the sentence intact.

---

## Translator's Foreword & Title Handling (`pipeline/assemble.py`)

- **Foreword auto-generation:** If a glossary exists, the assemble stage calls GPT-4o to generate a 250–400 word Translator's Foreword explaining the cultural translation philosophy and preserved terms. LLM sign-off placeholders are automatically cleaned.
- **Duplicate chapter title stripping:** The LLM translation often starts with "Chapter N: Title" which would duplicate the `<h1>` rendered by assemble. The stage detects and strips leading chapter headings (including multi-line subtitle continuations with em-dashes).
- **Book title derivation:** The manuscript title is extracted from the earliest translated chunk rather than using the ingested filename (which is often a placeholder).

---

## Future Extensibility

This architecture is designed to evolve:

1. **Additional source languages** — add language detection and language-specific chunking rules. Translation prompt is already parameterized by source language.
2. **Layout preservation** — OCR bounding boxes are stored from day one. A future `Layout` stage can use them to preserve original formatting in output.
3. **Human-in-the-loop review** — status flags (`needs_review`) on pages, terms, and translations enable a review UI without schema changes.
4. **Parallel book processing** — PostgreSQL advisory locks and per-book state allow multiple books to process concurrently.
5. **Alternative LLMs** — translation service is behind an interface. Swap GPT-4o for another model without touching pipeline logic.
6. **Streaming/event-driven** — stages currently run sequentially per book. Can be converted to event-driven (Service Bus/Event Grid) by publishing stage-completion events.
7. **Quality scoring** — a v1 Translation Quality Score is being defined (multilingual-embedding semantic similarity + reference-free MT QE + cross-family LLM judge on a sample). See `.squad/decisions/inbox/niobe-oracle-quality-score-brief.md` for the architecture; scores will attach to `Translation` records once Oracle ships the implementation.

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Staged pipeline, not event-driven | Simpler to reason about, debug, and resume. Event-driven is Phase 2 if needed. |
| PostgreSQL as source of truth | Relational model fits the hierarchical book→page→chunk→translation structure. JSONB for flexible metadata. |
| PostgreSQL for orchestration | Pipeline progress, advisory locks, stage state. Single data store — no separate cache layer to manage. |
| Idempotent stages | Books are expensive to process. Must be able to resume from any point. |
| JSON mode for LLM output | Structured extraction of translations + cultural terms in one call. More reliable than parsing free-form text. |
| Seed glossary + LLM detection | Pure LLM detection is unreliable for rare terms. Seed list catches the known ones; LLM catches the rest. |
| ePub-first, PDF from same source | Semantic HTML is the canonical format. ePub and PDF are both renderings of it. One source, two outputs. |
| Managed Identity everywhere | Zero secrets in code. Non-negotiable for production. |
