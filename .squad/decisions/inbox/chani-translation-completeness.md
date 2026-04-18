### Decision: Translation Completeness Enforcement

**Author:** Chani
**Date:** 2026-04-18
**Status:** Active
**Issue:** GitHub #8

Failed LLM translation calls no longer crash the pipeline. Instead, each failed chunk gets a placeholder: `[TRANSLATION FAILED — REVIEW REQUIRED]`. A `Translation` database record is created for every chunk (success or failure) so downstream stages always have complete data. A completeness check after the loop validates input/output counts match. `TranslateOutput.failed_count` reports how many chunks failed (default 0, backward compatible).

**Rationale:** Raw untranslated source text bleeding into output PDFs is unacceptable. Crashing on a single chunk failure is also unacceptable for long books (100+ chunks). The placeholder approach makes failures visible to reviewers without blocking the rest of the translation.

**Key constraint:** Sequential translation order preserved — context passing requires it. On failure, the last *successful* context is carried forward.

**Constant:** `TRANSLATION_FAILED_PLACEHOLDER` is a module-level constant in `translate.py`, importable by tests and downstream code.
