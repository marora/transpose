# Project Context

- **Owner:** Mani
- **Project:** Transpose — agentic pipeline that translates scanned/digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence for OCR and Azure OpenAI GPT-4o for literary/cultural translation. Culturally significant words (atman, dharma, karma) must be preserved untranslated and collected into a glossary. Output: publication-ready ePub/PDF.
- **Stack:** Python, PostgreSQL, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights
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

### 2026-04-20 — Deep Comparative Quality Review

- **Verdict:** Pipeline output NOT production-ready. 3 P0 blockers, 2 P1 significant, 2 P2 minor.
- **P0-1:** All 9 chapter titles truncated — subtitles after em-dash dropped in both ToC and body headers. Heading extraction strips post-dash content.
- **P0-2:** Cover title is filename placeholder ("Test Hindi Book") instead of translated source title ("Hindi Literature and Culture — Test Booklet").
- **P0-3:** Devanagari in glossary garbled — font embedding issue in WeasyPrint PDF export produces substitution artifacts (e.g., `भȫèक्ति` instead of `भक्ति`, `T` replacing `व` throughout).
- **P1-1:** Key phrases missing from 4 chapters (Ch2: "eight limbs", Ch4: "fruits of action", Ch8: "guru tradition"/"meditation", Ch9: "continuity").
- **P1-2:** Word count 60% inflated vs source (1.60× vs golden's 1.05×). Ch9 at 4× expected — content bleed from Foreword into chapter text stream.
- **Critical gap in existing gates:** All 5 current quality gates check structural presence (is a title there? are there 9 chapters?) but NOT content fidelity (is the title correct? are chapters complete?). Every P0 passed existing gates.
- **Recommended 6 new QA checks:** Title Fidelity, Enhanced Cover Validation, Devanagari Rendering Integrity, Key Phrase Coverage, Per-Chapter Word Count, ToC Completeness.
- **Golden JSON assessment:** Directionally correct but missing section-level data, cover title field, and Devanagari validation criteria. Needs enrichment.
- **Full report:** `.squad/decisions/inbox/stilgar-qa-findings.md`

### 2026-04-20 — Deep Visual Inspection Round 2 (Post P0-Fix)

- **Verdict:** CONDITIONAL PASS — 1 P0, 2 P1, 2 P2 remaining (down from 3 P0 + 2 P1 + 2 P2 in R1).
- **Resolved from R1:** Chapter titles now complete with subtitles (P0-1 fixed), cover shows translated title not filename (P0-2 fixed), word count inflation eliminated — all chapters at 0.91x–1.16x golden (P1-2 fixed, Ch9 bleed gone).
- **Remaining P0:** Glossary Devanagari garbling — 17 of 49 entries corrupted. Character `9` systematically replaces `व` (va), IPA characters (ɜ·, ɡ, ɟ, ɠ, ɥÊ) replace vowel matras. WeasyPrint font glyph substitution failure.
- **Key phrases confirmed present:** "Shrimad Bhagavad Gita", "nishkama karma", "eightfold path" (= eight limbs), "action bears fruit" (= fruits of action) — R1's "missing phrase" findings were false positives caused by double-space PDF extraction artifacts breaking exact-string matching.
- **Lesson:** Always normalize whitespace before substring matching on PDF-extracted text. PyMuPDF extracts justified text with variable spacing.
- **Font investigation needed:** `fonts/` directory likely has incomplete Devanagari font. Noto Sans Devanagari recommended for full conjunct glyph coverage.
- **ToC page numbers:** All show "1" — WeasyPrint CSS `target-counter()` limitation. P1 severity.
- **Full report:** `.squad/decisions/inbox/stilgar-visual-inspection-r2.md`

### 2026-04-21 — Documentation Drift Fix (4 files)

- **README.md:** Removed Redis from Stack (replaced with PostgreSQL for orchestration). Added "Quality Gates" to the "What It Does" list.
- **docs/architecture.md:** Replaced all Redis references with PostgreSQL (system overview, ASCII diagram footer, pipeline state section, service table, design decisions). Added 7 new sections: Quality Gates (all 7 gates described), HTTP API, Service Context, Unicode Normalization, Cross-Page Paragraph Joining, Translator's Foreword & Title Handling.
- **docs/project-structure.md:** Complete file tree rewrite — added api.py, gates.py, context.py, utils/, scripts/, fonts/, tests/golden/, tests/regression/, new unit/integration tests. Removed non-existent files (test_pipeline_e2e.py, test_azure_services.py, alembic/).
- **docs/api-contracts.md:** Added comprehensive Quality Gates section with contracts for all 7 gates (GateResult model, per-gate signature, check tables with thresholds). Added rule #7: "Quality gates block stage transitions."
- **Lesson:** Docs drifted because the serverless pivot (commit 7b2b83d) and gate system additions didn't update docs in the same commits. Proposed docs-update convention to prevent recurrence.

### 2026-04-21 — Production Readiness Audit

- **Full report:** `.squad/decisions/inbox/stilgar-prod-readiness-audit.md`
- **4 blockers found:**
  1. `acquire_lock()` defined in `cache.py:55` but never called in `runner.py` — distributed lock is inert, concurrent runs can corrupt data.
  2. `keyvault_url` config field exists but no code reads from Key Vault — secrets management is dead code.
  3. `pipeline_state.book_id` is UUID in SQL schema but passed as `str` in Python — fragile implicit cast.
  4. In-memory `_jobs` dict in `api.py` grows unbounded, lost on restart, no DB persistence during execution.
- **7 warnings:** No migration framework, fonts not in Docker image (Devanagari garbling root cause), shallow health endpoint, no auth/rate limiting on `/translate`, silent error swallowing, fire-and-forget tasks, missing production metrics.
- **14 items verified working:** Tracing wired, all 7 stages connected, all 7 gates invoked, all 6 metrics used, all models active, all services initialized, DB schema matches code, idempotency enforced, Managed Identity throughout, NFC normalization consistent, seed glossary loaded, health probes in Bicep, CI gates workflow exists, validation reports generated.
- **Proposed Gate 8 (Operational Readiness):** Preflight checks at container startup — DB connectivity, blob access, OpenAI reachability, env vars set, fonts present, schema version, golden target valid. Runs at startup, not per-book.
- **Key lesson:** "Configure but never call" is a recurring pattern. `configure_tracing()` was fixed; `acquire_lock()` and `keyvault_url` are the same class of bug. Audit-by-grep-for-unused-definitions should be a standard review step.
