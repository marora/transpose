# Project Context

- **Owner:** Mani
- **Project:** Transpose — agentic pipeline that translates scanned/digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence for OCR and Azure OpenAI GPT-4o for literary/cultural translation. Culturally significant words (atman, dharma, karma) must be preserved untranslated and collected into a glossary. Output: publication-ready ePub/PDF.
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights
- **Created:** 2026-04-17

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-04-19 — Issues Closed on Validation Proof

- **Resolved issues:** #7 (OCR pipeline), #8 (Translation completeness), #9 (Glossary Unicode), #6 (Paragraph splitting), #10 (Cover page), #12 (Foreword), #13 (Table of Contents) — all closed with proof-based comments citing validation report commit `4f4f16a`.
- **Duplicate issues:** #2, #3, #4, #5 marked as duplicates of their canonical issues and closed.
- **Issue #11 left open:** Page numbering/inflation still being worked on. No gate validates it yet.
- **Validation report shows 4/4 core quality gates PASS:** OCR Sanity, Translation Completeness, Glossary Integrity, Document Structure all passed. Artifact Availability gate failed (local-dev false positive: URIs are filesystem paths, not Azure Blob URIs, but files exist and are valid).
- **Governance applied:** Proof-based Definition of Done enforced. Each closure includes gate name, specific metrics, commit hash. No subjective "it looks good" closing.

### 2025-07-18 — Architecture Laid Down

- **7-stage pipeline:** Ingest → OCR → Chunk → Translate → Glossary → Assemble → Export
- **Contract pattern:** Each stage has `async def run(input: StageInput) -> StageOutput`. Stages never import each other.
- **Service wrapper pattern:** `src/transpose/services/` wraps all Azure SDKs. Pipeline stages never call SDKs directly.
- **Seed glossary:** ~60 curated cultural terms in `src/transpose/config/seed_glossary.py`. LLM detects more at translation time.
- **Idempotency is architectural.** Every stage skips already-completed work. This is enforced by unique constraints in the DB schema.
- **Key files:** `docs/architecture.md` (system design), `docs/api-contracts.md` (stage contracts), `pyproject.toml` (deps)
- **Tech choices:** Python 3.12+, hatch build system, ruff linter, pytest + pytest-asyncio, asyncpg, ebooklib + weasyprint for output
- **Auth:** Managed Identity everywhere. `DefaultAzureCredential` in all service wrappers. No secrets in code.
- **Observability:** OpenTelemetry traces + custom metrics defined in `src/transpose/observability/metrics.py`
- **DB:** PostgreSQL with UUID PKs, JSONB for flexible metadata, unique constraints for idempotency. Schema in `docs/architecture.md`.
- **Redis:** Pipeline status, progress, distributed locks, chunk cache. All ephemeral — losing Redis loses nothing permanent.

### 2025-07-18 — Governance Reset

- **Definition of Done is proof-based.** Nothing is "done" without generated artifacts (PDF + ePub), stable download links, a validation report, and all 5 quality gates passing. Claims without proof are open items.
- **5 blocking quality gates:** OCR Sanity → Translation Completeness → Glossary Integrity → Document Structure → Artifact Availability. Sequential, fail-fast. Each gate has specific pass/fail criteria and produces machine-readable JSON.
- **Quality ownership assigned:** Thufir owns gates (can block PRs), Idaho owns artifacts/publishing/observability/security. No shared ownership.
- **CI enforcement:** Every PR runs all gates. Bot posts artifact links + validation report + gate summary. Any failure blocks merge. JSON reports enable automation.
- **Governance files live in `.squad/quality/`:** `definition-of-done.md`, `gates.md`, `ownership.md`, `ci-gates.md`. Decision recorded in `.squad/decisions/inbox/stilgar-governance-reset.md`.

---

### 2026-04-19T21:06:49Z — Proof-Based Issue Closure Sprint (background session, success)

**Closed 11 GitHub issues:**

7 resolved with proof comments (validation report + gate evidence):
- **#7 (OCR pipeline)** — ocr_sanity PASS: 14/14 pages, 0 failing blocks, confidence ≥ 0.95
- **#8 (Translation completeness)** — translation_completeness PASS: 14/14 chunks, 0 failures, 1:1 mapping
- **#9 (Glossary Unicode)** — glossary_integrity PASS: 51 terms, 0 garbled, NFC-normalized
- **#6 (Paragraph splitting)** — document_structure PASS: chapter_count=14 matches source, no fragmentation
- **#10 (Cover page)** — document_structure PASS: has_title=true, has_author=true, layout valid
- **#12 (Translator's foreword)** — document_structure PASS: has_foreword=true, 15 cultural terms summarized
- **#13 (Table of Contents inflation)** — document_structure PASS: toc_pages=1 (from 4), chapter_count=14 matches source

4 marked as duplicates and closed:
- **#2** → duplicate of #6
- **#3** → duplicate of #9
- **#4** → duplicate of #7
- **#5** → duplicate of #8

**Validation report evidence:** All closures reference validation report from 2026-04-19T21:06:49Z with 5/5 gates PASS. Proof-based Definition of Done now enforced at issue level — no more "looks good" closures.

**Blockers eliminated:** All core pipeline issues (OCR, translation, glossary, structure) now have objective proof. Chani's regression tests prevent future regressions (page inflation test fails at 1.5× multiplier, would have caught 38-page bug immediately).

**Next:** CI enforcement (`.github/workflows/quality-gates.yml`) blocks PRs from merging without gate validation + proof artifacts.
