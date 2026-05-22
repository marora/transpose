# Skill: Pipeline Performance Diagnosis

**Slug:** pipeline-perf-diagnosis  
**Owner:** Trinity  
**Created:** 2026-05-21T23:02:20-04:00

---

## Summary
When a book run is unexpectedly slow, do not stop at stage timings. Verify whether concurrency knobs are **real, wired, and effective** for the specific stage, and separate repeated prompt overhead from payload tokens.

---

## Checklist

1. **Rank stages by elapsed time first**
   - Use actual run timings, not guesses.
   - Identify the single dominant stage before optimizing anything else.

2. **Verify concurrency in three layers**
   - **Config layer:** does a setting / env var exist (`*_CONCURRENCY`, `*_WORKERS`, `*_BATCH_SIZE`)?
   - **Wiring layer:** is the setting passed into the stage/client?
   - **Execution layer:** does the stage actually consume it (`asyncio.gather`, semaphore, worker pool, batch fan-out), or is it just stored?

3. **Check effective runtime inputs**
   - Inspect `.env`, deployment env vars, CLI/API overrides.
   - Distinguish "default stayed in effect" from "someone explicitly set it low".

4. **Use telemetry to validate code assumptions**
   - For translation, look at DB `translations.created_at` density / clustering.
   - For OCR, confirm whether pages were produced via a monolithic job or true batched fan-out.
   - If local logs only show a resume run, say so explicitly and lean on DB + code.

5. **Estimate prompt overhead separately from payload**
   - Tokenize the fixed system/user scaffold locally.
   - Multiply by chunk count to estimate repeated overhead.
   - Compare against actual prompt-token totals to see whether cost is mostly prompt framing or source payload.

6. **Search repo history before concluding "someone disabled it"**
   - Check git log for `sequential`, `serial`, `disable concurrent`, `rate limit`, `throttle`.
   - Review decisions log for explicit throttling decisions.
   - Absence of evidence matters: sometimes the issue is missing implementation, not a rollback.

---

## Heuristics

- **A knob that is only stored is not a feature.**
- **Stage-level sequential orchestration is normal; per-stage inner loops are where throughput lives.**
- **For LLM stages, high input:output ratios usually mean prompt-shape waste before model-quality waste.**
- **For OCR stages, a single long-running cloud poller is operationally serial even if the service parallelizes internally.**

---

## Shiv Sutra example
- OCR dominated wall time (~5h 47m) and had no real pipeline-side parallel fan-out.
- Translation had real async concurrency (default 5), but still spent most prompt tokens on repeated scaffold.
- Conclusion: the run was **partially parallelized**, not fully serialized and not fully parallelized.
