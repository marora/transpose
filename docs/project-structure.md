# Transpose — Project Structure

```
transpose/
├── pyproject.toml                  # Project metadata, dependencies, build config
├── README.md                       # Project overview and quickstart
├── docs/
│   ├── architecture.md             # System architecture (this is the bible)
│   ├── project-structure.md        # This file
│   └── api-contracts.md            # Stage input/output contracts
├── src/
│   └── transpose/
│       ├── __init__.py             # Package root, version
│       ├── cli.py                  # CLI entry point (run pipeline, check status)
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── runner.py           # Pipeline orchestrator — runs stages in sequence
│       │   ├── ingest.py           # Stage 1: PDF ingestion and registration
│       │   ├── ocr.py              # Stage 2: Text extraction via Document Intelligence
│       │   ├── chunk.py            # Stage 3: Semantic text chunking
│       │   ├── translate.py        # Stage 4: LLM translation with term preservation
│       │   ├── glossary.py         # Stage 5: Cultural term aggregation
│       │   ├── assemble.py         # Stage 6: Document reassembly
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
│       │   ├── ocr_client.py       # Azure AI Document Intelligence wrapper
│       │   ├── llm_client.py       # Azure OpenAI wrapper (translation calls)
│       │   ├── blob_client.py      # Azure Blob Storage wrapper
│       │   ├── database.py         # PostgreSQL connection and query helpers
│       │   └── cache.py            # Redis connection and pipeline state helpers
│       └── observability/
│           ├── __init__.py
│           ├── tracing.py          # OpenTelemetry trace setup
│           └── metrics.py          # Custom metrics definitions
├── tests/
│   ├── conftest.py                 # Shared fixtures (DB, Redis, mocks)
│   ├── unit/
│   │   ├── pipeline/
│   │   │   ├── test_ingest.py
│   │   │   ├── test_ocr.py
│   │   │   ├── test_chunk.py
│   │   │   ├── test_translate.py
│   │   │   ├── test_glossary.py
│   │   │   ├── test_assemble.py
│   │   │   └── test_export.py
│   │   ├── models/
│   │   │   └── test_models.py
│   │   └── services/
│   │       ├── test_ocr_client.py
│   │       ├── test_llm_client.py
│   │       └── test_blob_client.py
│   └── integration/
│       ├── test_pipeline_e2e.py
│       └── test_azure_services.py
├── alembic/                        # Database migrations (added when DB schema is implemented)
│   └── ...
└── infra/                          # Infrastructure-as-code (Bicep/Terraform — Idaho's domain)
    └── ...
```

## Conventions

- **src layout**: `src/transpose/` — prevents accidental import of uninstalled package
- **One model file per domain concept**: not one file per class, not one mega-file
- **Services wrap Azure SDKs**: pipeline stages never call Azure SDKs directly. Always through a service wrapper. This enables testing and future swaps.
- **Config via environment**: Pydantic `BaseSettings` reads from env vars. No config files in the repo (except seed glossary).
- **Tests mirror source**: `tests/unit/pipeline/test_ingest.py` tests `src/transpose/pipeline/ingest.py`
