### Decision: Distributed Lock Wiring + API Key Auth
**Author:** Chani  
**Date:** 2026-04-18  
**Status:** Active  

**B1 — acquire_lock() wired in runner.py:** After ingest produces the `book_id`, the runner now calls `acquire_lock(book_id)` before OCR. If the lock is already held (concurrent duplicate request), the pipeline returns early with `BookStatus.PROCESSING` and a `LockConflict` error — no expensive stages run. Existing `release_lock()` calls in success/failure paths remain unchanged.

**B8 — API key auth on /translate:** `api.py` now has an `api_key_middleware` that validates `Authorization: Bearer <key>` or `X-API-Key` headers against `TRANSPOSE_API_KEY` (env var via Settings). Permissive mode when the env var is unset (local dev). `/health` and `/status/{book_id}` remain unauthenticated for health probes. Uses `hmac.compare_digest` for timing-safe comparison.

**Impact:** All pipeline stages, API handlers, and tests. Idaho should ensure `TRANSPOSE_API_KEY` is set in Container Apps environment (Key Vault reference recommended).
