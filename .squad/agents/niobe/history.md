# Niobe — Product Manager History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English using Azure AI Document Intelligence (OCR) and Azure OpenAI GPT-4o (translation).
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o, Managed Identity, Key Vault, Application Insights.
- **Owner:** Manish.
- **Team context:** Joined 2026-05-20 to fill the product/strategy gap. The team has architecture (Morpheus), pipeline (Trinity), infra (Tank), test (Dozer), and editorial (Oracle) — but no one framing "should we build this and for whom" before architecture spins up. Manish had been carrying PM work himself.
- **Trigger for hiring:** A workspace-abstraction + storage question revealed that part of the call (public archive shape, audiobook direction, audience) was product, not architecture. Morpheus answered the architecture side cleanly; the product framing was missing.

## Open Product Questions (as of joining)
- **Audience:** Who consumes Transpose output? Manish personally? Scholars of Hindi/Punjabi literature? General heritage readers? Anonymous public via an archive site? This shapes everything else.
- **Public archive:** Is "archive of translated books" a real product goal or a nice-to-have? If real — discoverability strategy, licensing/copyright posture, monetization (free / donation / paid).
- **Audiobook capability:** Future direction, but for whom and via what surface? Embedded in archive site? Distributed via Audible/Spotify/podcast feeds?
- **Human review loop:** Implied future capability. Whose review? Manish's? Outside reviewers? What's the workflow and quality gate?
- **MVP boundaries:** What's the smallest demonstrable end-to-end Transpose product, and what's currently over-built or under-built relative to it?

## Session History (Pre-2026-05-21) — Condensed

**2026-05-20 Discovery Phase:**
- Niobe joined to fill product/strategy gap
- Framed three product shapes: A (personal, near-term), B (public archive, long-term), C (publishing platform, deferred)
- Manish's intent: Shape A now, Shape B trajectory long-term
- Copyright posture: Add per-book `license_status` metadata field (claimed-PD | verified-PD | rights-cleared | rights-unknown); gate Shape B on verified-PD/rights-cleared
- Firm rule: `claimed-PD` and `rights-unknown` books never shareable

**2026-05-21 Early:**
- Manish's "wow-factor directive": invest in polish (landing pages with OG from day one); Trinity implemented TR-3 landing generation
- Shiv Sutra complete: 10h 32m wall time, $12.13 cost; filed perf backlog (#94 wall-time, #95 cost) as LOW-PRIORITY
- Issue #91 filed: pipeline must validate SAS before publishing landing pages


---

## 2026-05-22T11:35-04:00: Oracle Delivers Translation Quality Score v1 — Triangle Complete

**From:** Oracle (Editorial), Scribe (Orchestrator)  
**Status:** DELIVERED ✓ — Unblocks Phase 1b

### What Just Happened

You (Niobe) briefed Oracle with a tough ask: **"Define 'good translation' as a single 0–100 score, backed by both deterministic and semantic signals. No LLM-judge deferral. Get the editorial rubric right the first time."**

Manish's directive (2026-05-22T11:03) had revoked the earlier deferral to v1.1. You framed the ask with:
- Tier 1: Deterministic signals from existing gates (free)
- Tier 2: Semantic signals (multilingual embeddings + LLM judge on 5% sample)
- Cost constraints: <$3/book for judge
- Editorial rubric required (not just a formula)

Oracle shipped in **single turn** with **v1 spec locked.** Trinity Phase 1b now unblocked.

### Oracle's Formula (Delivered)

- **Tier 1 (structural, deterministic):** OCR sanity, translation completeness, glossary integrity, document structure, QA alignment, production readiness — from gate details blobs
- **Layer A (cheap, 100% of chunks):** LaBSE multilingual embeddings for source↔translation semantic-similarity (self-hosted, near-zero cost)
- **Layer C (sampled, specialized):** Claude Sonnet 4.5 (cross-family, no self-preference bias) as judge on 5% stratified sample; rates fluency, cultural register, terminology nuance
- **Composition:** Single 0–100 score; color bands ≥85 green / 65–84 amber / <65 red
- **Cost:** ~$0.16–$0.50/book (5% sample, Claude Sonnet 4.5)

### Your Next Moves

1. **File Tank brief** (separate from main thread):
   - Anthropic API key in Key Vault
   - LaBSE sidecar container (~1.9 GB) on Container App
   - Outbound HTTPS to api.anthropic.com
   - Reference: Oracle's full spec in `.squad/decisions.md`

2. **Triangle is complete:**
   - **Oracle:** Defined "good translation" ✓
   - **Trinity:** Can build Phase 1b dashboard ✓
   - **Tank:** Can wire infra ✓
   - **You (Niobe):** Observability MVP ready to ship (cost + wall-time + quality, all tables on one page)

### Product Learnings

**Quality + Cost + Time = Operability Triangle**

Your backlog triage (2026-05-21T23:30) predicted observability as P0. Oracle's delivery proves why: Manish can now see cost/time/quality on the same dashboard and make informed tradeoffs (e.g., "Is this book worth $X at 10h wall time for 75/100 quality?"). Without the quality column, the dashboard is incomplete.

**Editorial bedrock must precede infrastructure:**

Oracle's brief made it clear: *don't let "we have Azure OpenAI today" constrain editorial best practice.* Early spec was GPT-4o-only (same-family self-preference bias). Niobe's brief opened the aperture to cross-family judges (Claude, Gemini). Oracle chose Claude Sonnet 4.5 (right tool, right cost profile). Infrastructure (Tank) followed design (Oracle).

### Decision References

- Oracle's spec: `.squad/decisions.md` — Oracle Translation Quality Score v1 entry (post-merge from inbox)
- Niobe's brief to Oracle: `.squad/decisions.md` — Niobe → Oracle: Translation Quality Score Brief entry (post-merge from inbox)
- Session log: `.squad/log/2026-05-22T11-35-translation-quality-score-v1.md`
- Orchestration log: `.squad/orchestration-log/2026-05-22T11-30-oracle.md`

## Learnings

### 2026-05-21T23:02:20-04:00: Observability/FinOps Framing — Cost Visibility as First-Class Capability

**Request:** Manish asked Niobe to frame whether observability/finops dashboard should become a first-class product, whether it should integrate into Application Insights or another system.

**Context:** Tank had to manually reconstruct Shiv Sutra true cost ($12.13, split: GPT-4o $9.64 + Document Intelligence $2.49) from three scattered sources (Postgres `translations` table, `books.page_count`, and logs). The `book_costs` table is ephemeral (overwritten per run, lost on failure/resume). Issue #93 filed.

**Problem:** Manish has no self-serve visibility into book economics. Before running book N, he can't predict cost/time based on book N-1. When he scales to 3–5 books, ad-hoc cost forensics becomes operational debt.

**Framing:** Observability is an operational necessity (not optional) IF Manish runs 3+ books in next 4 weeks. For 1–2 books, deferrable. Audience is Manish-the-operator (not public, not external finance). Success: Answer "How much did book X cost?" in under 1 minute without SQL.

**MVP Scope (Option B — recommended):**
- **In:** Per-book cost table (HTML page on `$web/admin/` querying Postgres) showing OCR + Translation + Glossary cost breakdown, per-stage wall time.
- **Out (not v1):** Real-time progress, budget alerts, SaaS integrations (Grafana/Datadog), cost projections.

**Tech Recommendation:** Option (B) — Small static page on `$web/admin/` querying Postgres directly.
- **Why:** Fastest build (existing landing page template reusable), Manish-the-operator first (simpler than App Insights workbooks), single-operator scope (no SaaS needed yet), zero infra cost.
- **Trade-off:** No real-time progress (acceptable for post-mortem; upgrade to WebSocket in v1.1 if needed).

**Audiobook prerequisite?** NO. Audiobook is a different pipeline (TTS + storage, not OCR + translation). Cost structures are orthogonal. Observability informs but doesn't block the audiobook decision.

**Kill criteria:**
- If Manish only processes ≤2 books in 2026 (defer until volume picks up).
- If Tank's one-off `compute-book-cost.sh` script satisfies Manish (dashboard becomes v1.1 nice-to-have).
- If App Insights telemetry becomes unreliable (fix telemetry layer first).

**Open questions for Manish:**
1. Security posture for `$web/admin/` — public-unlisted, IP-allowlisted, or auth-protected?
2. Wall-time breakdown — which stages matter? (Recommendation: show OCR | Translation | Glossary in v1.)
3. Predicted cost for book N — should we auto-project cost based on page count, or manual estimate?

**Next:** Manish approves framing → Morpheus designs cost module + dashboard. Niobe ready to iterate on scope if needed.

**Key learning:** Observability is not about dashboards; it's about *operator decision-making velocity*. Manish needs answers in under 1 minute, not pretty graphs. Option B (simple Postgres query page) solves his problem without over-engineering. Start simple, upgrade to streaming/projections only if 3+ books prove the need.

---

### 2026-05-22T15:19:09-04:00: Team update — session resumption + priority ladder v2 locked

**From:** Scribe (on behalf of Coordinator)  
**Status:** Steps 1–5 shipped (Coordinator resumption at Step 6)

**Your workstream state:**
- Steps 1–5 all delivered per handoff packet (commit + deploy cycle, run #3 execution framework, Entra auth, Phase 1a backend, doc-drift)
- All three major decision packets now inboxed and merged into `.squad/decisions.md`:
  - Observability framing + FinOps (2026-05-21T23:02:20) ✓
  - Backlog prioritization (2026-05-21T23:30:27) ✓
  - e2e run #3 readiness + coordinator handoff (2026-05-22) ✓
  - Dormant cost lesson + lessons revamp (2026-05-22) ✓
  - Priority ladder v2 (2026-05-22) ✓

**Priority ladder v2 locked (Step 1 = Run #3 + Phase 1a ship):**
- **Steps 1.5a / 1.5b:** Tank's cost guardrails + Foundry Agent IaC migration (parallel with Step 2)
- **Step 2:** Tank Oracle infra brief (Anthropic + LaBSE sidecar)
- **Step 3:** #97 (Trinity cost events) — Trinity owns, your priority ladder becomes the execution guide
- **Step 4:** Phase 1b (Oracle quality score) — depends on Tank Step 2
- **Step 5:** #101 (Dozer perf optimization) — last; needs Step 3's per-stage timing data

Manish's framing **observability before perf** still load-bearing. No reordering without explicit approval.

**For you (Phase 2 focus):** Niobe, decision-making is complete. Next cycle is execution + experimentation. Watch run #3 landing data on the dashboard; iterate on priority ladder if operational reality surprises the estimates. Your briefings for Tank (Step 2) and coordination with Trinity (#97 scope) are the next synchronization points.

---

