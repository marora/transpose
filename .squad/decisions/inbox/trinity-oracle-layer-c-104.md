# Trinity Decision Drop — Oracle Layer C Implementation (#104)

**Date:** 2026-05-23T07:45:00Z  
**Agent:** Trinity (Pipeline Dev)  
**Issue:** #104  
**PR:** #116 (merged to master)  
**Status:** ✅ Shipped

---

## Summary

Implemented Oracle Translation Quality Score Layer C — Anthropic Claude Sonnet 4.5 judge for post-export, non-blocking quality assessment on stratified 5% chunk sample. Complements Layer A (LaBSE embeddings) with cross-family LLM judgment to reduce GPT-4o self-preference bias.

---

## Key Decisions

### 1. Key Vault Secret Name

**Decision:** Assume secret name is `anthropic-api-key` (lowercase-kebab).

**Rationale:** Matches Tank's naming convention from existing secrets (`azure-openai-key`, `entra-client-secret`, `appinsights-connection-string` per `infra/modules/container-app.bicep:111`). Tank is working on #103 in parallel and will pick the final name. If Tank chooses differently, this is a one search-replace fix.

**Documented in:** `src/transpose/config/settings.py:36` — `anthropic_api_key: str = ""` field with comment referencing Key Vault.

**Follow-up for Scribe/Tank:** If Tank's #103 uses a different secret name, update the settings.py field name and the constant reference in oracle_judge.py imports.

---

### 2. oracle_score Schema

**Decision:** JSONB column in `book_validation_reports` table.

**Schema:**
```sql
ALTER TABLE book_validation_reports
ADD COLUMN oracle_score JSONB;
```

**Payload structure:**
```json
{
  "composite_score": 0-100,
  "fluency": 0-100,
  "cultural_register": 0-100,
  "terminology_nuance": 0-100,
  "sampled_chunk_ids": ["uuid1", "uuid2", ...],
  "raw_judge_response": "{...full JSON from Anthropic...}"
}
```

**NULL semantics:** oracle_score is NULL when:
- Layer C has not run (pre-export, gate failure, or resumed run skipping export)
- Anthropic API call failed (logged, non-blocking)
- API key not configured (local dev without .env)

**Migration:** `migrations/versions/4b7d8e92f5a2_add_oracle_score_to_validation_reports.py` — alembic migration applied on next deploy. Also includes inline `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `database.py:ensure_validation_reports_table()` for safety.

**Dashboard surfacing:** `get_latest_validation_report()` includes oracle_score in response. Admin dashboard API returns it as-is; frontend renders raw JSON in Phase 1a (rich rendering deferred to Phase 1b/#109).

---

### 3. Stratified Sampling Algorithm

**Decision:** 3-way bin split (early/mid/late document sections) with proportional sample allocation.

**Algorithm:**
1. Split chunks into early (0–33%), mid (33–67%), late (67–100%) bins
2. Target sample size = max(1, floor(total × 0.05))
3. Allocate target across bins: per_bin = target // 3, remainder goes to early bin
4. random.sample() from each bin (min of per_bin or bin size)
5. Sort result by sequence to maintain document order

**Edge case handling:**
- **Very small books (≤3 chunks):** Skip stratification, use direct random.sample()
- **Empty bins:** Check `if bin:` before random.sample() to avoid ValueError
- **Safety net:** `if not sample and chunks: sample = [random.choice(chunks)]` — always return at least 1 chunk

**Learning:** Stratified sampling requires careful edge case handling. Bins can be empty when `total < 3 × per_bin`. Always ensure minimum 1 chunk sampled.

**Implementation:** `src/transpose/observability/oracle_judge.py:select_stratified_sample()`

---

### 4. Anthropic SDK Integration Pattern

**Decision:** asyncio-native client wrapper, single API call per book with batched sample payload.

**Client config:**
- SDK: `anthropic>=0.39.0` (added to `pyproject.toml`)
- Timeout: 120s (matches existing LLM client timeout in `llm_client.py`)
- Model: `claude-sonnet-4-5-20250514` (hardcoded constant)
- Temperature: 0.0 (deterministic scoring)

**Prompt design:**
- **System prompt:** Sets scholarly context (spiritual/philosophical literature, cultural term preservation, fluency vs. accuracy trade-offs)
- **User prompt:** Batches all sampled chunks (source + translation pairs) into one prompt
- **Output format:** JSON-only response with 4 scores (composite, fluency, cultural_register, terminology_nuance)

**Error handling:**
- try/except wrapper in `judge_translation_quality()` — returns None on any Anthropic SDK exception
- JSON parsing errors → returns None (logged)
- Missing required fields in response → returns None (logged)

**Implementation:** `src/transpose/observability/oracle_judge.py:_call_anthropic_judge()`

---

### 5. Dashboard Surfacing Approach

**Decision:** Surface raw oracle_score JSON in validation reports; rich rendering deferred to Phase 1b.

**Phase 1a (this PR):**
- `database.py:get_latest_validation_report()` includes oracle_score in response payload
- Admin dashboard API returns it as-is (no transformation)
- Frontend displays raw JSON (read-only, no quality color bands yet)

**Phase 1b (future, #109):**
- Extract composite_score into a dedicated column in the books table
- Render quality color bands (≥85 green, 65–84 amber, <65 red per Oracle spec)
- Display sampled chunk drill-down (show which chunks were assessed)
- Link to raw_judge_response for full Anthropic output

**Rationale:** Minimal dashboard delta for Phase 1a (just surface the data). Rich rendering requires frontend work and is blocked on Tank's Layer A infra (#103) landing first.

---

### 6. Non-Blocking Error Path in Pipeline

**Decision:** try/except wrapper in `runner.py` post-export hook. Errors logged, never raised. Pipeline continues with oracle_score=NULL.

**Implementation:**
```python
oracle_score_payload = None
if book_id and ctx.settings.anthropic_api_key:
    try:
        oracle_score = await judge_translation_quality(...)
        if oracle_score:
            oracle_score_payload = {...}
    except Exception as exc:
        logger.error("Oracle Layer C failed (non-blocking): %s", exc, exc_info=True)
```

**Error propagation:** Never raises. If Anthropic API times out, crashes, or returns invalid JSON, pipeline completes normally with oracle_score=NULL in DB.

**Rationale:** Oracle Quality Score is observability, not a quality gate. Layer C failure should never block a book export.

---

## Follow-Up Actions (Not in This PR)

1. **Tank #103 coordination:** Verify Key Vault secret name matches assumption (`anthropic-api-key`). If different, update settings.py constant.
2. **Container App env var wiring:** Add `TRANSPOSE_ANTHROPIC_API_KEY` secret reference in `infra/modules/container-app.bicep` (small bicep tweak, Tank owns).
3. **Phase 1b dashboard (#109):** Surface oracle_score.composite_score in validation reports table (frontend + API changes, not pipeline).

---

## Reusable Patterns

### Post-Export Non-Blocking Observability Hook

```python
# Pattern: Execute observability layer post-export, never block pipeline
observability_payload = None
if book_id and ctx.settings.observability_api_key:
    try:
        result = await run_observability_layer(...)
        if result:
            observability_payload = {...}
    except Exception as exc:
        logger.error("Observability layer failed (non-blocking): %s", exc, exc_info=True)

# Always persist, even if observability failed
await _persist_validation_report(ctx, book_id, report, observability_payload)
```

**Use when:** Any post-export observability layer that should never block the pipeline (quality scoring, telemetry enrichment, external integrations).

---

### Stratified Chunk Sampling

```python
def select_stratified_sample(chunks, fraction=0.05):
    if not chunks:
        return []
    target = max(1, int(len(chunks) * fraction))
    if len(chunks) <= 3:
        return random.sample(chunks, min(target, len(chunks)))
    # 3-way bin split with proportional allocation...
```

**Use when:** Need representative sample across document structure (early/mid/late) for quality assessment, A/B testing, or telemetry.

---

## Cost Model

**Per-book cost:** ~$0.16–$0.50 (15 chunks × ~1.5K tokens/sample × $0.003 input + $0.015 output)

**Breakdown:**
- Input: ~22.5K tokens (15 samples × 1.5K source+translation per sample)
- Output: ~300 tokens (JSON response with 4 scores)
- Model: claude-sonnet-4-5-20250514 ($3/$15 per 1M tokens)

**Cost control:** Sample fraction is configurable (default 0.05 = 5%). Can reduce to 0.03 (3%) if cost is concern.

---

## Test Coverage

**Tests:** `tests/unit/observability/test_oracle_judge.py` (12 tests, all passing)

**Coverage areas:**
- Stratified sampling edge cases (empty, single chunk, tiny fractions)
- Anthropic client mocking (success path + error paths)
- JSON parsing validation (invalid JSON, missing fields)
- Non-blocking error handling (API failure, no API key)

**Run with:** `pytest tests/unit/observability/test_oracle_judge.py -q`

---

**End of decision drop.**
