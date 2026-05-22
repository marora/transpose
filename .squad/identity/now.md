---
updated_at: 2026-05-21T23:02:20Z
focus_area: Observability framing + parallelization audit. Audiobook deferred pending observability decision.
active_issues: ["#94 wall-time", "#95 cost", "#96 OCR batching", "#93 durable cost tracking"]
---

# What We're Focused On

**Shiv Sutra is complete and production-ready.** Pipeline hardened (glossary U+FFFD scrub, export gate heuristics calibrated). Performance baseline documented (10h 32m wall time, $12.13 cost for 250-page book). Parallelization audit complete; observability framing drafted. Team now awaiting Manish decisions on two fronts before proceeding to next phase.

## Current Session (2026-05-21T23:02:20Z)

### Trinity — Parallelism Audit ✅ Complete

Investigated Shiv Sutra's 10h 32m wall time. **Findings:**
- **Translation:** Parallelization active (concurrency=5, asyncio.gather + semaphore working; 8–11 chunks/min)
- **OCR:** Configured but non-functional (single entire-PDF job, not batched; accounts for 55% of wall time)

**Proposed next steps:**
1. Increase translation concurrency 5 → 8 (low-risk, quota-dependent) — awaiting Manish quota approval
2. Implement OCR batching (Issue #96; real code work, 50–60% wall-time upside)
3. Reduce repeated prompt cost (future optimization)

**Constraint:** Manish issued directive "Parallelization MUST be enabled at all times; 10-hour wall time is unacceptable." No changes proceed without explicit approval.

### Niobe — Observability / FinOps Framing ✅ Complete

Shiv Sutra cost took 5+ minutes to reconstruct manually from scattered DB sources. Frames observability as first-class capability.

**Recommended solution:** Option B — static HTML page on `$web/admin/` querying Postgres directly. Success = answer cost/time in <1 minute without SQL/grep.

**MVP scope (v1):**
- Per-book cost table (total, breakdown by OCR | Translation | Glossary, page count, wall time, stage durations)
- Cost calculation module (utility; sum tokens, price against rate card)
- Durable `book_costs` rows (fixes Issue #93)

**Out of scope (v1):**
- Real-time progress (WebSocket infrastructure)
- Cost projections (need 3–5 books history)
- Enterprise finops integration

**Open questions for Manish:**
1. Security: IP allowlist, auth, or public for `$web/admin/`?
2. Wall-time granularity: which stages separately?
3. Cost prediction: linear scaling or defer?

**Audiobook dependency:** NO. Cost structures orthogonal (TTS vs. OCR+translation). v1 is PDF-only; audiobook telemetry added to same dashboard when it ships (v1.1).

## Decision Gates Pending

**Manish must decide:**

1. **Parallelism defaults:** Approve Trinity's 5→8 translation concurrency (quota-dependent)?
2. **Observability MVP:** Approve Niobe's Option B framing (static page, Postgres direct-query)?
3. **Audiobook timeline:** Proceed before or after observability? (Independent, but informs roadmap)

If parallelism approved → Trinity/Tank implement (quota review + default changes).
If observability approved → Morpheus designs → Trinity/Tank implement (cost module + dashboard + Issue #93 fix).

## Recent Session History (2026-05-20 through 2026-05-21)

- **Issue #89 (FIXED):** Glossary U+FFFD character contamination — defensive final scrub + 5 unit tests
- **Issue #90 (FIXED):** export_rendering false positive on single repeated images — threshold raised to ≥2 distinct images
- **Shiv Sutra E2E:** Pipeline ran to completion with validation=PASS; 275KB ePub and 1.38MB PDF published to Azure
- **Public Access (FIXED):** Republished artifacts to `$web/shiv-sutra/` (Static Website path). User-accessible at `https://transposebooks.z13.web.core.windows.net/shiv-sutra/`
- **Landing Page Complete:** Both download buttons (source + translation) now functional and visible
- **Infrastructure Wiring:** `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` now flows through IaC and setup scripts
- **Performance Telemetry:** Baseline cost + wall-time analysis complete; parallelism investigation complete
- **Unit test suite:** 353 tests, all passing

## Next: Decision Implementation + Multi-Book Scale

Once Manish approves parallelism + observability decisions:
1. Apply translation concurrency defaults (or implement OCR batching if quota permits)
2. Build observability v1 (cost module + dashboard + Issue #93 fix)
3. Ingest 3–5 additional books with improved parallelization + cost visibility
4. Monitor wall time + cost performance on multi-book runs
5. Re-evaluate audiobook direction post-observability

**Hardening roadmap:** Still on track. Shiv Sutra production-ready. Ready for volume once decisions land.


