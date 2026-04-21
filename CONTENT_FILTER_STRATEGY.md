# Content Filtering Strategy for Transpose

## Executive Summary
Azure OpenAI's content filter is blocking ~2-3% of chunks in spiritual/religious texts (Osho, Bhagavad Gita). Current implementation has no fallback—blocked chunks receive permanent `[TRANSLATION FAILED]` placeholders. This document provides a comprehensive 5-part strategy addressing immediate code fixes, Azure configuration, prompt engineering, fallback chain design, and error classification.

---

## 1. IMMEDIATE FIXES (Code Changes)

### 1.1 Error Classification: Distinguish Content Filter Blocks from Transient Errors

**Problem:** `llm_client.py:79-97` retries ALL exceptions 3 times. Content filter blocks (permanent failures) get the same treatment as rate limits (transient). This wastes 6+ seconds per blocked chunk.

**Fix:** Catch `openai.APIStatusError` and inspect the error code.

```python
# In llm_client.py, after line 97:

from openai import APIStatusError, RateLimitError
from typing import Literal

class TranslationError(Exception):
    """Base exception for translation errors."""
    def __init__(self, message: str, error_type: Literal["content_filter", "rate_limit", "transient", "unknown"]):
        super().__init__(message)
        self.error_type = error_type

async def _call_with_retry():
    try:
        return await client.chat.completions.create(...)
    except APIStatusError as e:
        # Azure OpenAI returns 400 for content policy violations
        if e.status_code == 400 and "content_policy_violation" in str(e.message).lower():
            raise TranslationError(
                f"Content filter block: {e.message}",
                error_type="content_filter"
            )
        elif e.status_code == 429:
            raise TranslationError(
                f"Rate limit: {e.message}",
                error_type="rate_limit"
            )
        else:
            # Transient: 500, 503, timeouts, connection errors
            raise TranslationError(
                f"Transient error (HTTP {e.status_code}): {e.message}",
                error_type="transient"
            )
    except Exception as e:
        raise TranslationError(str(e), error_type="unknown")
```

**Retry Strategy Update:** Only retry transient errors; fail fast on content filters.

```python
@retry(
    retry=retry_if_exception_type(TranslationError),
    stop=stop_after_attempt(1),  # Don't retry content filter blocks
    reraise=True,
)
async def _call_with_retry():
    ...
```

---

### 1.2 Add `error_type` and `error_reason` Fields to Translation Model

**Problem:** When a chunk fails, there's no record of WHY it failed (content filter vs. rate limit vs. timeout).

**Fix:** Update `src/transpose/models/translation.py`:

```python
@dataclass
class Translation:
    chunk_id: UUID
    book_id: UUID
    translated_text: str
    model_version: str
    cultural_terms: list[ExtractedTerm] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: dict = field(default_factory=dict)
    error_type: str | None = None  # "content_filter", "transient", "rate_limit", etc.
    error_reason: str | None = None  # Full error message for debugging
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

Update `translate.py:195-206` to capture error details:

```python
except TranslationError as exc:
    logger.warning(f"Translation failed for chunk {chunk.id}: {exc.error_type} - {exc}")
    failed_count += 1

    placeholder = Translation(
        chunk_id=chunk.id,
        book_id=input.book_id,
        translated_text=TRANSLATION_FAILED_PLACEHOLDER,
        model_version="n/a",
        cultural_terms=[],
        prompt_tokens=0,
        completion_tokens=0,
        raw_response={},
        error_type=exc.error_type,  # NEW
        error_reason=str(exc),  # NEW
    )
    await ctx.db.create_translation(placeholder)
```

---

### 1.3 Add Request Timeout to LLM Calls

**Problem:** Azure OpenAI API calls have no timeout. Slow provider responses can hang for 5+ minutes per request.

**Fix:** Update `llm_client.py:33-38`:

```python
self._client = AsyncAzureOpenAI(
    azure_endpoint=self._endpoint,
    azure_deployment=self._deployment,
    api_version=self._api_version,
    azure_ad_token_provider=token_provider,
    timeout=30.0,  # Add explicit timeout: 30 seconds
)
```

---

## 2. AZURE-SIDE OPTIONS (Configuration & Governance)

### 2.1 Request Content Filter Exemption (Preferred)
**Action:** Contact Azure support to add the Transpose deployment to the **content filter exemption list** for specific prompts/use cases.

- **Deployment:** `gpt-4o` (TRANSPOSE)
- **Use Case:** Literary translation of religious/spiritual texts (Osho, Bhagavad Gita, Sufi poetry)
- **Severity Levels to Exempt:** `sexual:high`, `self_harm:high` (depending on corpus)
- **Supporting Evidence:** Osho's "Vigyan Bhairav Tantra" blocked 2/72 chunks; all false positives (tantric philosophy, not pornography)

**Impact:** Eliminates filter blocks on religious/philosophical content permanently.

---

### 2.2 Alternative: Deploy a Regional Replica with Relaxed Filtering

If exemption is denied:

1. Deploy a **secondary GPT-4o deployment** in a different Azure region with looser content policy settings (if available).
2. Implement **fallback routing:** If region-1 blocks, retry on region-2.

**Code:** Update `llm_client.py` to support multiple deployments:

```python
class LlmClient:
    def __init__(self, endpoints: list[dict], deployment: str, api_version: str):
        self._endpoints = endpoints  # [{"endpoint": "...", "region": "east"}, ...]
        self._deployment = deployment
        self._api_version = api_version
        self._clients = {}  # One client per endpoint
        self._current_endpoint_idx = 0

    async def translate_chunk(...):
        for attempt, endpoint_config in enumerate(self._endpoints):
            try:
                return await self._call_with_retry(endpoint_config)
            except TranslationError as e:
                if e.error_type == "content_filter" and attempt < len(self._endpoints) - 1:
                    logger.warning(f"Content filter on region {endpoint_config['region']}, trying next...")
                    continue
                raise
```

**Cost:** Additional $X/month for secondary deployment, but eliminates manual recovery labor.

---

### 2.3 Monitor Azure Content Filter Metrics

Enable **Application Insights logging** for content filter blocks:

```python
# In llm_client.py after catching content filter error:
from transpose.observability.metrics import content_filter_blocks

content_filter_blocks.add(1, {
    "book_id": str(book_id),
    "severity": "high",  # Extract from error details
    "chunk_sequence": chunk.sequence,
})
```

This allows dashboards to track filter false-positive rate and request exemption adjustments.

---

## 3. PROMPT ENGINEERING (Reduce Filter Triggers)

### 3.1 Deprioritize Sensitive Language in Prompts

**Problem:** Prompts mentioning certain cultural terms might trigger the filter pre-emptively.

**Fix:** Update `llm_client.py:146-184` (_build_system_prompt):

```python
prompt = f"""You are a literary translator specializing in {lang_name} to English translation.

TASK: Translate the provided text maintaining literary and cultural authenticity.

CULTURAL CONTEXT:
This is a translation of {lang_name} spiritual and philosophical literature. 
Some content may contain mature themes including tantric philosophy, sexuality in religious context, 
and descriptions of bodily practices. These are presented in an educational and philosophical 
context and should be translated with academic integrity and precision.

CRITICAL RULES:
1. Preserve cultural and spiritual terms in transliterated form (e.g., dharma, karma, guru).
2. For preserved terms, provide the original script and a brief definition.
3. Maintain narrative flow and literary tone.
4. Translate all content accurately; do not censor or modify language due to mature themes.
5. If the original text contains explicit descriptions, translate them faithfully—do not euphemize.

[rest of prompt...]
"""
```

This **contextualizes** sensitive content as educational rather than triggering filter defaults.

---

### 3.2 Use Neutral Synonyms in Intermediate Steps

If a chunk repeatedly fails, the fallback chain (see Section 4) can attempt a **rephrased request**:

```python
# In translate.py, if error_type == "content_filter":
async def retry_with_rephrased_context(chunk, seed_terms):
    """Retry translation with depersonalized framing."""
    logger.info(f"Retrying chunk {chunk.id} with alternative prompt framing...")
    
    # Use more formal/academic language
    alt_prompt = f"""Academic translation task: {chunk.source_text}
    
    Provide this in academic English suitable for scholarly publication."""
    
    return await ctx.llm.translate_chunk(
        source_text=alt_prompt,
        source_language=book.source_language,
        seed_terms=seed_terms,
    )
```

---

## 4. FALLBACK CHAIN (When Blocks Occur)

### 4.1 Staged Fallback Strategy

When `error_type == "content_filter"`:

1. **Attempt 1:** Rephrase prompt with academic framing (Sec 3.2)
2. **Attempt 2:** Route to secondary deployment (Sec 2.2, if available)
3. **Attempt 3:** Use GPT-3.5-Turbo deployment (faster, may have different filter tuning)
4. **Attempt 4:** Queue for human translator (mark chunk as `needs_review=True`)
5. **Attempt 5:** Use placeholder for now, allow publishing with redacted footnote

**Code Structure:**

```python
# In llm_client.py:

async def translate_chunk_with_fallback(
    self,
    source_text: str,
    source_language: SourceLanguage,
    previous_context: str | None = None,
    seed_terms: dict[str, tuple[str, str]] | None = None,
) -> TranslationResponse:
    """Translate with multi-stage fallback for content filter blocks."""
    
    fallback_strategies = [
        ("rephrased_prompt", self._translate_with_academic_framing),
        ("secondary_region", self._translate_on_secondary_deployment),
        ("faster_model", self._translate_with_gpt35turbo),
        ("human_review", self._queue_for_human_review),
    ]
    
    for strategy_name, strategy_fn in fallback_strategies:
        try:
            logger.info(f"Attempting translation: strategy={strategy_name}")
            return await strategy_fn(
                source_text=source_text,
                source_language=source_language,
                previous_context=previous_context,
                seed_terms=seed_terms,
            )
        except TranslationError as e:
            if e.error_type != "content_filter":
                raise  # Don't fallback on transient errors
            logger.warning(f"Strategy {strategy_name} failed, trying next...")
            continue
    
    # All fallback strategies exhausted
    raise TranslationError(
        f"Translation blocked by content filter and all fallback strategies exhausted. "
        f"Chunk requires manual human translation.",
        error_type="content_filter_unrecoverable"
    )
```

---

### 4.2 Human-in-the-Loop: Staging for Manual Translation

Add a **manual_translation** table in the database:

```sql
CREATE TABLE manual_translation_queue (
    id UUID PRIMARY KEY,
    chunk_id UUID NOT NULL,
    book_id UUID NOT NULL,
    source_text TEXT NOT NULL,
    reason ENUM('content_filter_block', 'llm_quality_issue', 'cultural_sensitivity') NOT NULL,
    assigned_to UUID,  -- translator ID
    translated_text TEXT,
    status ENUM('pending', 'in_progress', 'completed', 'rejected') DEFAULT 'pending',
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

When fallback is exhausted:

```python
# In translate.py:
if isinstance(exc, TranslationError) and exc.error_type == "content_filter_unrecoverable":
    logger.info(f"Queuing chunk {chunk.id} for manual translation review...")
    manual_tx = ManualTranslation(
        chunk_id=chunk.id,
        book_id=input.book_id,
        source_text=chunk.source_text,
        reason="content_filter_block",
    )
    await ctx.db.create_manual_translation_queue_item(manual_tx)
    
    # Use placeholder in output
    translation = Translation(
        chunk_id=chunk.id,
        book_id=input.book_id,
        translated_text="[MANUAL TRANSLATION REQUIRED — see manual_translation_queue]",
        model_version="n/a",
        error_type="content_filter_unrecoverable",
        error_reason="Blocked by content filter; queued for human review.",
    )
```

---

## 5. ERROR CLASSIFICATION (Distinguishing Failure Types)

### 5.1 Extended Translation Model with Error Metadata

See Section 1.2 above. New fields:

- `error_type: str | None` — "content_filter", "rate_limit", "transient", "timeout", "parsing", "unknown"
- `error_reason: str | None` — Full error message
- `retry_count: int` — How many times was this chunk retried?
- `fallback_strategy_used: str | None` — Which fallback was successful (if any)

---

### 5.2 Observability: Metrics and Logging

Add to `metrics.py`:

```python
from opentelemetry.sdk.metrics import Counter, Histogram

# Counters
translation_errors_by_type = Counter(
    "transpose.translation.errors.by_type",
    "Translation errors classified by type",
    unit="1",
)
content_filter_blocks = Counter(
    "transpose.translation.content_filter.blocks",
    "Chunks blocked by content filter",
    unit="1",
)
fallback_strategy_invocations = Counter(
    "transpose.translation.fallback.invocations",
    "Fallback strategy attempts",
    unit="1",
)

# Histograms
translation_retry_count = Histogram(
    "transpose.translation.retry.count",
    "Number of retries per chunk",
    unit="1",
)
translation_recovery_time = Histogram(
    "transpose.translation.recovery.time",
    "Time to recover from content filter block (if successful)",
    unit="ms",
)
```

Update `translate.py` to emit these metrics:

```python
except TranslationError as exc:
    translation_errors_by_type.add(1, {"error_type": exc.error_type, "book_id": str(input.book_id)})
    
    if exc.error_type == "content_filter":
        content_filter_blocks.add(1, {"book_id": str(input.book_id)})
```

---

### 5.3 Queries for Operational Dashboards

```sql
-- What % of chunks are blocked by content filter?
SELECT 
    book_id,
    COUNT(*) as total_chunks,
    COUNT(CASE WHEN error_type = 'content_filter' THEN 1 END) as filter_blocks,
    ROUND(100.0 * COUNT(CASE WHEN error_type = 'content_filter' THEN 1 END) / COUNT(*), 2) as filter_block_pct
FROM translations
GROUP BY book_id
HAVING COUNT(CASE WHEN error_type = 'content_filter' THEN 1 END) > 0
ORDER BY filter_block_pct DESC;

-- Which chunks are blocked (for manual intervention)?
SELECT chunk_id, book_id, error_reason, created_at
FROM translations
WHERE error_type = 'content_filter'
ORDER BY created_at DESC;

-- Fallback strategy success rate
SELECT 
    fallback_strategy_used,
    COUNT(*) as attempts,
    COUNT(CASE WHEN translated_text != '[TRANSLATION FAILED]' THEN 1 END) as successes,
    ROUND(100.0 * COUNT(CASE WHEN translated_text != '[TRANSLATION FAILED]' THEN 1 END) / COUNT(*), 2) as success_rate
FROM translations
WHERE fallback_strategy_used IS NOT NULL
GROUP BY fallback_strategy_used;
```

---

## Implementation Roadmap

### Phase 1: Immediate (This Sprint)
- [ ] 1.1 Implement `TranslationError` with error_type classification
- [ ] 1.2 Add error_type and error_reason to Translation model
- [ ] 1.3 Add request timeout to LLM client
- [ ] 2.1 Request Azure content filter exemption

### Phase 2: Fallback & Human-in-the-Loop (Sprint 1)
- [ ] 3.1 Update system prompt with academic framing
- [ ] 4.1 Implement staged fallback chain
- [ ] 4.2 Create manual_translation_queue table
- [ ] 5.1–5.3 Add metrics and observability

### Phase 3: Secondary Deployment (Sprint 2, if exemption denied)
- [ ] 2.2 Deploy secondary GPT-4o in alternate region
- [ ] Update LlmClient to support multi-endpoint routing

---

## Expected Impact

| Issue | Fix | Expected Outcome |
|-------|-----|------------------|
| #34 | Exemption request + fallback chain | 100% of spiritual texts translatable |
| #48 | Error classification | No more wasted retries on permanent failures |
| #51 | Fallback strategies + manual queue | Content-filtered chunks are now recoverable |
| Osho E2E run | All three | 72/72 chunks completed, 0 placeholders |

---

## Risk Mitigation

**What if Azure denies the exemption request?**
- Fallback to Phase 3 (secondary deployment in alternate region)
- Manual translation queue becomes permanent workflow for religious/spiritual texts

**What if secondary deployment also filters?**
- Escalate to human translator for editorial decision
- Document exemption request reasoning for next attempt

**What if fallback chain becomes expensive?**
- Monitor cost via metrics (see Section 5.2)
- Prioritize exemption request (lowest cost, permanent fix)
- Batch problematic books for manual translation

---
