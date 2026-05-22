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

## Session History (Pre-2026-05-21)

**2026-05-20:** Niobe joined to fill product strategy gap. Framed three distinct questions bundled in Manish's workspace/archive/audiobook request: (1) workspace abstraction (technical debt), (2) public archive (product shape), (3) audiobook capability (distribution). Identified three product shapes: Shape A (personal translation tool, local/private), Shape B (curated public archive, metadata + free downloads), Shape C (publishing platform, multi-format + review). Parsing Manish's intent revealed trajectory thinking: near-term Shape A, long-term Shape B. Recommended building workspace storage layer now (works for all shapes), deferring archive UI/audiobook/review until shape is named.

**2026-05-20 (Afternoon):** Manish answered Q1 — "For now it will be only me...longterm goal is a steadily built archive/repository." Signals: near-term = Shape A + tight circle + URL-protected; long-term = Shape B + open access + global scope (not just Hindi/Punjabi). Strategic shift: "enable the trajectory" — build Shape A now, keep Shape B reachable per-book.

**2026-05-20 (Late):** Manish answered Q2 — copyright posture "generally considered public-domain work." Legal reality: source text (ancient Sanskrit) likely PD, but PDF edition (publisher commentary/typesetting) has fresh copyright; translation is his, but derivative of potentially copyrighted PDF. PM move (Path 2): Don't gatekeep; add per-book `license.status` (claimed-PD | verified-PD | rights-cleared | rights-unknown) and `provenance.source` fields. Shape A: any status fine. Shape B: gate on verified-PD or rights-cleared. Manish approved; enables trajectory without legal overreach.

**2026-05-20 (Final):** Product brief locked. Scope: build Shape A now (personal workbench + private URL share), defer Shape B + audiobook + review workflow, add license/provenance schema to workspace. Key learning: Manish prefers "structured metadata field to make decision explicit per book" over "architectural gatekeeping." Trust + transparency > control.

**2026-05-20 (Final):** Four open architecture questions answered. Firm rules: (1) `claimed-PD` and `rights-unknown` books never shareable; only `verified-PD` and `rights-cleared` qualify for Shape A URL. (2) Azure subscription active. (3) Share both source + translated PDFs; WhatsApp preview (OpenGraph) deferred to Phase 2 (Shape B archive UI). (4) PDF ownership is third-party internet sources; start with `rights-unknown`, research per-book. Key learning: Manish's "keep them private" closes copyright-risk gap. Third-party PDFs + no chain of custody = always start `rights-unknown`.

**2026-05-21T04:39:36Z:** Manish's wow-factor directive — "Invest in polish (landing pages with OG previews from day one)." Overrides earlier MVP-minimalism recommendation. Trinity built landing page generation (TR-3) with Open Graph + Twitter Card meta tags. Books have public-but-unindexed landing pages from pipeline day one. Key learning: User priorities can override initial MVP framing. Manish's judgment is sound — early readers' first impression drives feedback quality. Polish is worth the small cost.

**2026-05-21T12:17:57Z:** Issue #91 — Dead download links on existing landing pages. Pipeline must validate SAS generation before publishing landing page. If SAS fails, fail Stage 8 or publish with disabled buttons + error. Owner: Trinity (pipeline fix).

**2026-05-21T14:41:45Z:** Trinity's performance optimization backlog. Shiv Sutra: 10h 32m wall time ($12.13 cost). Filed #94 (wall-time target <2h) and #95 (cost target <$5). Both LOW-PRIORITY; focus on hardening, not optimization. If Shape B scales up, cost per book will inform monetization model (free/donation/paid).

---

## Learnings (Active)

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

