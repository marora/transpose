# Decision: Test Isolation for pydantic-settings

**Author:** Thufir  
**Date:** 2026-04-22  
**Status:** Active  

## Context

`tests/unit/test_settings.py::test_defaults` has been failing since the `.env` file was added to the repo root. The `Settings` class uses `env_file=".env"` in `model_config`, which causes pydantic-settings to read the file and override code defaults during tests.

## Decision

Use `Settings(_env_file=None)` in all test code that needs to verify code defaults. Additionally, temporarily strip `TRANSPOSE_*` environment variables during default-checking tests to prevent CI env vars from leaking in.

Helper function `_clean_settings()` encapsulates this pattern.

## Impact

- All agents writing tests that instantiate `Settings` should use `_env_file=None` unless specifically testing `.env` file loading behavior.
- This pattern applies to any pydantic-settings class in the project.

## Team Notes

- The `.env` file contains real Azure credentials — it should be in `.gitignore` (it appears to be tracked). Idaho may want to address this.
- Lock acquisition tests (`test_acquire_lock_called_before_ocr`, `test_pipeline_aborts_when_lock_fails`) are xfailing until Chani wires `acquire_lock()` in runner.py. They will automatically pass once the B1 fix lands.
- API auth tests use a simulated middleware matching the B8 spec. Once Chani commits the real middleware, `_make_app()` will detect it and use the real implementation transparently.
