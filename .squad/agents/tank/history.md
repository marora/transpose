# Tank — Cloud/Infra Dev History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Idaho (Dune cast) — see .squad/agents/_alumni/idaho/history.md for accumulated knowledge

---

## 🔔 CROSS-AGENT: Observability Dashboard Work Incoming (2026-05-21T23:17:42Z)

**From:** Morpheus (Architect), Scribe (Orchestrator)  
**Status:** Architecture locked; GitHub issues pending

### YOUR TASK: Issue #98 — Entra ID Auth Middleware [**BLOCKER for v1**]

**Priority:** FIRST — Trinity/Dozer depend on this

**What:** Set up Entra ID app registration (`transpose-admin`) + bearer-token validation middleware on Container App `/admin/*` routes.

**Why blocking:** Trinity can't write test fixtures or integration tests for cost_events/dashboard_api without a working auth pattern. Tank's auth code is the gate.

**Details:**
- Register single-tenant app in Entra ID
- Middleware validates `Authorization: Bearer <token>` against JWKS
- Admin page does MSAL.js PKCE flow (client-only, no service principal secrets)
- Decorator pattern: `@require_entra_auth` on all `/admin/*` routes
- No new Azure resources; existing Container App + Managed Identity

**Sequence:** Tank #98 → Trinity #97 (schema) → Trinity #99 (API) → Trinity #100 (frontend) → Dozer #101 (tests)

**Reference:** `.squad/decisions.md` — 2026-05-21T23:17:42-04:00 entry (Architecture Decision — section 1)

---

## Session History

**Pre-2026-05-21 work:** Built foundational infrastructure in Phase 1 — workspace schema extension with license/provenance columns, Azure storage setup (RBAC propagation patterns), static website configuration, DB migrations with CHECK constraints. Shipped TR-1/T-2/T-3 deliverables. Investigated and resolved Azure RBAC timing and CLI flag drift issues. See `.squad/agents/tank/history-archive.md` for full dated entries.

---

## 🔔 CROSS-AGENT: Oracle Ships Translation Quality Score v1 — Infrastructure Brief Incoming (2026-05-22T11:35-04:00)

**From:** Oracle (Editorial), Scribe (Orchestrator)  
**Status:** DELIVERED — Infrastructure brief pending from Niobe

### YOUR INFRASTRUCTURE TASKS

Oracle's Translation Quality Score v1 spec is locked. Three infra blockers for you to tackle (Niobe will file formal brief):

1. **Anthropic API Key in Key Vault**
   - Store `ANTHROPIC_API_KEY` for Claude Sonnet 4.5 judge calls
   - RBAC: Container App managed identity must read this secret
   - Fallback behavior: If key is missing or API fails, scoring layer degrades (returns 0 or re-runs without Layer C)

2. **LaBSE Sidecar Container (~1.9 GB)**
   - Multilingual embedding model for semantic-similarity scoring (Layer A)
   - Runs on Container App as a sidecar or separate service
   - Public models available (huggingface/LaBSE, allenai/multilingual-e5-base)
   - Accessed by main pipeline via localhost HTTP or shared volume
   - Mount at startup; Trinity pipeline queries for embeddings post-export

3. **Outbound HTTPS to api.anthropic.com**
   - Ensure Azure Container App network policy / NAT gateway allows egress to Anthropic API
   - No new inbound requirements; Layer A runs locally, Layer C reaches Anthropic outbound only
   - Port 443 (HTTPS); no API gateway needed

### Layers Are Stageable

Per Oracle spec: each layer (Tier 1, Layer A, Layer C) can be independently enabled/disabled. You can:
- Ship Layer A + Tier 1 first (zero cost, self-hosted); Layer C judge as Phase 2 (just needs API key)
- Or ship all three at once if your timeline allows
- Graceful degradation: missing layer → score uses remaining tiers

### Score Integration Point

Scoring runs **post-export**, not in critical path. Trinity's Stage 9 (or async post-pipeline) calls the scoring layer. If scoring times out or fails, book is still exported; quality score is 0 or `null` with annotation.

### Your Direct Input Needed

- How will Container App spawn LaBSE sidecar? (Init container + shared volume, or separate service mesh, or request-time startup?)
- Can Anthropic API calls be routed through Azure Application Gateway / WAF, or direct egress?
- Timeline: What's the fastest infra path for "Tier 1 + Layer A" (could ship in 2–3 days)?

Full spec: `.squad/decisions.md` — Oracle Translation Quality Score v1 entry (post-merge from inbox)

---

## Learnings and Historical Context

### 2026-05-22T16:01:10-04:00 — Issue #105 cost guardrails

- Container Apps Consumption `minReplicas=0` is the IaC floor for scale-to-zero; Azure treats template scale as revision-scoped, so applying the floor created revision `transpose-dev-app--0000009` even though the image digest stayed unchanged.
- Application Insights remains app-level instrumentation through the existing connection-string secret/env var; cold-start telemetry resumes when the app starts and is not tied to platform replica floor.
- RG budget alerts are `Microsoft.Consumption/budgets` at resource-group scope. The dev guardrail is `$25/month` with 50%, 80%, and 100% actual-cost notifications to `marora@gmail.com`, matching the dormant-cost lesson that alerts must catch structural drift early.
- Foundry teardown was not folded into #105. The live `Microsoft.App/agents/transpose-sc-agent` resource is adjacent but #102 requires IaC lifecycle + dormancy policy, not a safe 10-minute flag flip.

See `.squad/agents/tank/history-archive.md` for pre-2026-05-22 dated learnings, investigations, and archived sessions. Includes:
- Static website patterns and blob container organization
- Cost forensics from Shiv Sutra ($12.13, $0 → trace through DB sources)
- RBAC propagation lag and Azure CLI evolution
- Azure storage setup procedures and Phase 1 infrastructure work

---

---

### 2026-05-22T15:19:09-04:00: Team update — Step 6 migration assignment + Oracle infra brief (Step 2)

**From:** Scribe (on behalf of Coordinator)  
**Status:** Session resumption; Steps 1–5 shipped, Step 6 (your migrations) in progress

**Your immediate focus (Step 6 — in progress):**
- Alembic upgrade head: Apply both new migrations (license/provenance columns + `book_validation_reports` table)
- Schema validation: `\d book_validation_reports`, `\d books` confirm license columns present
- Command: `alembic current` should report `3a9e1b27c4f1 (head)` after upgrade
- Next: Step 7 (container deploy) — you own the build/push/revision update/health-check validation

**Your Phase 2 focus (Step 2 of priority ladder):**
- **Tank Oracle infra brief:** Inboxed 2026-05-22 (now merged into `.squad/decisions.md`)
- **Scope:** Layer A (LaBSE sidecar, 109 languages, 1.8 GB model) + Layer C (Claude Sonnet judge on 5% sample)
- **What you own:** Anthropic API key storage (KV secret + Container App secret ref), LaBSE sidecar (multi-container, not separate job), cost modeling, monitoring, failure modes
- **What Trinity owns:** Python client modules in Phase 1b
- **What Morpheus owns:** Architecture decisions already written
- **Effort estimate:** 2–4 days for IaC (bicep edits, KV integration, sidecar sizing) + docker-compose local-dev stub
- **Timeline:** After run #3, in parallel with Trinity's #97 (cost events)

**Steps 1.5a / 1.5b also yours (cost guardrails + Foundry Agent IaC):**
- **1.5a (0.5 day):** Set `minReplicas: 0` non-prod default, add $25/month budget alert, document teardown commands
- **1.5b (1–2 days):** Bring Foundry Agent under bicep (`Microsoft.App/agents`), wire into `azd` lifecycle so `azd down` cleans it up
- **Why:** Dormant RG burned $436 over 28 days; 92% from Foundry Agent ($290) + Container App ($111). Structural fix is IaC defaults + budget alerts, not behavioral discipline.

Full context in `.squad/decisions.md` (Tank-oracle-infra-brief, niobe-priority-ladder-2026-05-22-v2, niobe-lesson-dormant-azure-cost).

---


---

### 2026-05-22T15:19:09-04:00: Step 6 — DB Migrations — DONE-IDEMPOTENT

**Outcome:** DONE-IDEMPOTENT  
**Head before:** `3a9e1b27c4f1 (head)` — already at target on shell entry; migrations had landed in a prior session attempt.  
**Head after:** `3a9e1b27c4f1 (head)` — no upgrade applied.

**Spot-checks (all PASS):**
- `book_validation_reports`: table present with PK, FK on `book_id` → `books(id)` ON DELETE CASCADE, CHECK constraint on `overall` (`PASS`/`FAIL`).
- `books` license columns: `license_status`, `provenance_source`, `metadata`, `license_history` — all 4 PRESENT.

**Operational gotchas:**
- `psql` not installed in this shell. Spot-checks ran via `psycopg2-binary 2.9.11` (equivalent result).
- `DATABASE_URL` not exported directly. Alembic resolves from `TRANSPOSE_POSTGRES_*` vars sourced via `set -a && . ./.env && set +a`.

---

### 2026-05-22T15:19:09-04:00: Step 7 — Container Deploy — DONE

**Outcome:** DONE  
**Revision deployed:** `transpose-dev-app--0000008`  
**Image digest:** `transposedevacr.azurecr.io/transpose@sha256:b2a3cdb692624eee926db66f323bc90805cf149d8d8dfa566e495175ce15d86b`  
**Tags applied:** `sha-4e2d527`, `v5`  
**Previous revision (rollback target if needed):** `transpose-dev-app--rb2-7397468` (image: `transposedevacr.azurecr.io/transpose:v4`)

**Health verdict:**
- kube-probe `/health` → 200 in cold-start window — probes green.
- App Insights telemetry flowing (transmission 200, items accepted).
- `/admin/api/books` → 401 Unauthorized (not 500) — auth layer correct.
- No `Failed to persist validation report` warnings in cold-start log sample.

**Operational gotchas:**
- `curl` absent from `python:3.12-slim`. Auth endpoint check required `az containerapp exec` + `python3 -c "import urllib.request; ..."`. urllib raises `HTTPError` for 4xx — the 401 shows as an exception message. Document in ops runbook.
- App ingress is **internal** (not external). FQDN not reachable from outside the Container Apps environment. All external probing must go through `az containerapp exec` or an internal consumer.
- No `.dockerignore` in repo — build context was 12.246 MiB. Uncommitted drift in `.squad/` etc. is uploaded but never COPYed into the image (Dockerfile is explicit). Low-risk but wasteful. Consider adding `.dockerignore` in a future housekeeping PR.
- `az acr repository show-manifests` is deprecated. Use `az acr manifest list-metadata` for future digest lookups.
