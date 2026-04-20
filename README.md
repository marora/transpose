# Transpose

Agentic pipeline for translating scanned or digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence and Azure OpenAI GPT-4o.

## What It Does

1. **Ingests** a PDF (scanned or digital)
2. **Extracts text** via OCR (Azure AI Document Intelligence) or direct text extraction
3. **Chunks** text into translation-ready segments respecting semantic boundaries
4. **Translates** each chunk with GPT-4o, preserving culturally significant terms (*atman*, *dharma*, *karma*, *seva*, *sangat*...)
5. **Builds a glossary** of preserved cultural terms with definitions
6. **Assembles** a structured manuscript with chapters and glossary
7. **Exports** publication-ready ePub and PDF
8. **Quality Gates** — blocking checks between every stage validate OCR sanity, translation completeness, glossary integrity, document structure, artifact availability, and golden-target QA before the pipeline advances

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system design.

## Stack

- **Runtime:** Python 3.12+
- **OCR:** Azure AI Document Intelligence
- **Translation:** Azure OpenAI GPT-4o
- **Database:** PostgreSQL (persistent state + pipeline orchestration)
- **Compute:** Azure Container Apps
- **Auth:** Managed Identity + Key Vault
- **Observability:** Application Insights (OpenTelemetry)

## Development

```bash
# Install in development mode
pip install -e ".[dev,test]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Usage

```bash
# Translate a book
transpose run --source /path/to/book.pdf --title "My Book" --language hindi

# Check pipeline status
transpose status --book-id <uuid>
```

## Project Structure

See [docs/project-structure.md](docs/project-structure.md).
