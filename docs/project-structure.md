# Transpose — Project Structure

```
transpose/
├── pyproject.toml                  # Project metadata, dependencies, build config
├── README.md                       # Project overview and quickstart
├── validation-report.json          # Pipeline validation output (generated)
├── docs/
│   ├── architecture.md             # System architecture (this is the bible)
│   ├── project-structure.md        # This file
│   └── api-contracts.md            # Stage input/output contracts
├── fonts/
│   ├── NotoSansDevanagari.ttf      # Devanagari font for PDF rendering
│   ├── NotoSansDevanagari-Regular.ttf
│   └── NotoSansGurmukhi.ttf        # Gurmukhi font for Punjabi rendering
├── scripts/
│   ├── create_test_pdf.py          # Generate a test Hindi PDF for local dev
│   ├── e2e_validation_run.py       # End-to-end pipeline validation script
│   └── generate_golden_target_pdf.py  # Produce golden-target English PDF
├── src/
│   └── transpose/
│       ├── __init__.py             # Package root, version
│       ├── api.py                  # HTTP API endpoint (aiohttp, port 8000)
│       ├── cli.py                  # CLI entry point (run pipeline, check status)
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── runner.py           # Pipeline orchestrator — runs stages in sequence
│       │   ├── gates.py            # Quality gates — blocking checks between stages
│       │   ├── ingest.py           # Stage 1: PDF ingestion and registration
│       │   ├── ocr.py              # Stage 2: Text extraction via Document Intelligence
│       │   ├── chunk.py            # Stage 3: Semantic text chunking (cross-page joining)
│       │   ├── translate.py        # Stage 4: LLM translation with term preservation
│       │   ├── glossary.py         # Stage 5: Cultural term aggregation
│       │   ├── assemble.py         # Stage 6: Document reassembly (foreword, dedup titles)
│       │   └── export.py           # Stage 7: ePub/PDF rendering
│       ├── models/
│       │   ├── __init__.py
│       │   ├── book.py             # Book, Page data models
│       │   ├── translation.py      # Chunk, Translation, CulturalTerm models
│       │   ├── glossary.py         # Glossary, GlossaryEntry models
│       │   ├── manuscript.py       # Manuscript, Chapter models
│       │   └── enums.py            # BookStatus, SectionType, SourceLanguage enums
│       ├── config/
│       │   ├── __init__.py
│       │   ├── settings.py         # Pydantic settings (env-based configuration)
│       │   └── seed_glossary.py    # Curated cultural term seed list
│       ├── services/
│       │   ├── __init__.py
│       │   ├── context.py          # ServiceContext — DI container for all service clients
│       │   ├── ocr_client.py       # Azure AI Document Intelligence wrapper
│       │   ├── llm_client.py       # Azure OpenAI wrapper (translation calls)
│       │   ├── blob_client.py      # Azure Blob Storage wrapper
│       │   ├── database.py         # PostgreSQL connection and query helpers
│       │   └── cache.py            # PostgreSQL-backed pipeline state tracking
│       ├── utils/
│       │   ├── __init__.py
│       │   └── unicode.py          # NFC normalization for Indic scripts
│       └── observability/
│           ├── __init__.py
│           ├── tracing.py          # OpenTelemetry trace setup
│           └── metrics.py          # Custom metrics definitions
├── tests/
│   ├── conftest.py                 # Shared fixtures (DB, mocks)
│   ├── fixtures/
│   │   ├── sample_hindi_text.txt
│   │   ├── sample_ocr_response.json
│   │   ├── sample_punjabi_text.txt
│   │   └── test-hindi-10page.pdf
│   ├── golden/
│   │   ├── README.md               # Golden reference documentation
│   │   ├── golden-target.json      # Expected output structure for QA gate
│   │   ├── golden-target-english.pdf
│   │   ├── golden-source-fingerprint.json
│   │   ├── expected-glossary.json
│   │   ├── expected-structure.json
│   │   └── gate-expectations.json
│   ├── unit/
│   │   ├── pipeline/
│   │   │   ├── test_ingest.py
│   │   │   ├── test_ocr.py
│   │   │   ├── test_chunk.py
│   │   │   ├── test_translate.py
│   │   │   ├── test_glossary.py
│   │   │   ├── test_assemble.py
│   │   │   ├── test_export.py
│   │   │   ├── test_gates.py       # Quality gate unit tests
│   │   │   └── test_runner.py      # Pipeline runner unit tests
│   │   ├── models/
│   │   │   └── test_models.py
│   │   ├── services/
│   │   │   ├── test_ocr_client.py
│   │   │   ├── test_llm_client.py
│   │   │   ├── test_blob_client.py
│   │   │   ├── test_cache.py       # Pipeline state tests
│   │   │   └── test_database.py
│   │   ├── test_export_visual.py   # Visual rendering tests
│   │   ├── test_seed_glossary.py
│   │   └── test_settings.py
│   ├── integration/
│   │   ├── test_cultural_preservation.py  # Cultural term preservation tests
│   │   └── test_pipeline_flow.py          # End-to-end pipeline flow
│   └── regression/
│       ├── conftest.py             # Regression-specific fixtures
│       ├── test_golden_reference.py       # Golden reference comparison
│       ├── test_golden_target_integrity.py # Golden target validation
│       ├── test_golden_targeted_qa.py     # Gate 6 regression tests
│       └── test_production_readiness.py   # Gate 7 regression tests
└── infra/                          # Infrastructure-as-code (Bicep/Terraform — Idaho's domain)
    └── ...
```

## Conventions

- **src layout**: `src/transpose/` — prevents accidental import of uninstalled package
- **One model file per domain concept**: not one file per class, not one mega-file
- **Services wrap Azure SDKs**: pipeline stages never call Azure SDKs directly. Always through a service wrapper. This enables testing and future swaps.
- **ServiceContext for DI**: `services/context.py` holds all initialized clients; stages receive `ctx` parameter.
- **Quality gates between stages**: `pipeline/gates.py` enforces blocking checks. No stage runs until its predecessor's gate passes.
- **Config via environment**: Pydantic `BaseSettings` reads from env vars. No config files in the repo (except seed glossary).
- **Tests mirror source**: `tests/unit/pipeline/test_ingest.py` tests `src/transpose/pipeline/ingest.py`
