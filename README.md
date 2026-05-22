# Transpose

Agentic pipeline for translating scanned or digital PDF books from Hindi/Punjabi into English using Azure AI Document Intelligence and Azure OpenAI GPT-4o.

## What It Does

1. **Ingests** a PDF (scanned or digital)
2. **Extracts text** via OCR (Azure AI Document Intelligence) or direct text extraction
3. **Chunks** text into translation-ready segments respecting semantic boundaries
4. **Translates** each chunk with GPT-4o, preserving culturally significant terms (*atman*, *dharma*, *karma*, *seva*, *sangat*...)
5. **Builds a glossary** of preserved cultural terms with definitions
6. **Assembles** a structured manuscript with chapters and glossary
7. **Exports** publication-ready ePub and PDF
8. **Quality Gates** — 10 blocking checks across the pipeline validate OCR sanity, translation completeness, glossary integrity, document structure, artifact availability, golden-target QA, production readiness, source-output structural parity, and operational readiness. See [docs/architecture.md](docs/architecture.md#quality-gates-pipelinegatespy) for the full catalog.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system design.
Admin dashboard auth is documented in [docs/auth.md](docs/auth.md).

## Stack

- **Runtime:** Python 3.12+
- **OCR:** Azure AI Document Intelligence
- **Translation:** Azure OpenAI GPT-4o
- **Database:** PostgreSQL (persistent state + pipeline orchestration)
- **Compute:** Azure Container Apps
- **Auth:** Managed Identity + Key Vault
- **Observability:** Application Insights (OpenTelemetry)

## Development

```bash
# Install in development mode
pip install -e ".[dev,test]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Usage

```bash
# Translate a book
transpose run --source /path/to/book.pdf --title "My Book" --language hindi

# Check pipeline status
transpose status --book-id <uuid>
```

## Project Structure

See [docs/project-structure.md](docs/project-structure.md).

---

## Architectural Progression / Lessons Learned

A durable record of the architectural calls this project has made and the *reasoning* behind them. The bullet-level changelog tells you what changed; this section exists so future contributors (agents, operators, future-Manish) inherit the *why*. Entries are short prose: context → decision → lesson → citation.

**Maintenance convention (Scribe-owned):** when a decision file lands in `.squad/decisions/inbox/` that captures an architectural lesson (not just a task assignment), the lesson is pulled into this section as part of the normal merge process. Inbox files remain the primary record; this section is the curated narrative on top.

### 1. Dormant Azure dev environments are not free — set `minReplicas: 0` and budget alerts before walking away

A dev/sandbox resource group (`transpose-sc`) accrued **~$436 over 28 dormant days** (≈ $15.60/day, ~$468/month projected if untouched) **before any real usage resumed**. The RG was provisioned in late April and left idle for ~4 weeks. Despite zero application traffic, cost continued to accrue because several Azure resources bill for provisioned capacity, not invocations.

**Where the money went (Apr 22 → May 19, dormant window):**

| Resource | Type | Dormant total | $/day idle | Billing model |
|---|---|---|---|---|
| `transpose-sc-agent` | Foundry Agent (`Microsoft.App/agents`) | $289.97 | $10.36 | Flat-rate provisioned 24/7 |
| `transpose-dev-app` | Container App | $111.14 | $3.97 | `minReplicas ≥ 1` keeps a container alive |
| `transpose-dev-psql` | PostgreSQL Flexible Server | $18.36 | $0.66 | Compute always-on unless explicitly stopped |
| `transposedevst` | Storage account | $9.00 | $0.32 | Capacity only |
| `transposedevacr` | Container Registry | $4.66 | $0.17 | Flat SKU price |
| `transpose-dev-openai` | Azure OpenAI | $2.70 | $0.10 | Token-based — behaved correctly (no idle billing) |
| `transpose-dev-logs` / `vault` | Log Analytics / Key Vault | <$0.30 | negligible | — |

**92% of dormant spend came from just two resources** — the Foundry Agent and the Container App.

**Confirmation the pattern is structural, not usage-driven:** after work resumed (May 20–22), per-day cost for the Foundry Agent ($8.95/day) and Container App ($3.24/day) was the same or lower than during dormancy. The charges aren't traffic-driven. The only resource that jumped under real usage was `transpose-dev-openai` (28×), which is exactly the correct behavior for a pay-per-token service.

**Root causes:**
1. **Foundry Agents bill 24/7 for provisioned capacity** regardless of invocation count. Easy to forget once deployed.
2. **Container Apps default to `minReplicas: 1`** in many templates — a single always-on replica is ~$120/month.
3. **PostgreSQL Flexible Server compute is billed while running**, even with zero connections. Must be explicitly stopped.
4. **No cost guardrails** were in place — no budget alert, no scheduled scale-down.

**Remediation (the runbook before walking away from a dev env):**

```bash
SUB=<subscription-id>
RG=transpose-sc
# 1) Scale Container Apps to zero
az containerapp update -g $RG -n transpose-dev-app --min-replicas 0 --subscription $SUB
# 2) Stop PostgreSQL (resumes in seconds)
az postgres flexible-server stop -g $RG -n transpose-dev-psql --subscription $SUB
# 3) Foundry Agent — delete via `az` for now; durable fix is Step 1.5b (bring under bicep + azd lifecycle)
#    Manual provisioning was the root cause of forgetting it for 28 days. (~$300/month idle.)
```

**Bake in by default (Tank-owned IaC follow-up — see Steps 1.5a and 1.5b of the priority ladder):**
- Set Container App `minReplicas: 0` in Bicep/Terraform for non-prod environments. *(Step 1.5a)*
- Add an Azure Budget alert on the RG at $25/month so a dormant burn is caught in days, not weeks. *(Step 1.5a)*
- **Foundry Agent should be in bicep under `azd` lifecycle so `azd down` cleans it up automatically. Manual provisioning was the root cause of forgetting it for 28 days.** *(Step 1.5b)*
- Tag resources with `env=dev` + `auto-shutdown=true` and consider an Azure Automation runbook that stops them nightly.
- For Foundry Agents specifically: once under IaC (Step 1.5b), `azd down` is the disposition command. No more "remember to delete it manually."

**The lesson:** in a serverless-coded stack, it's natural to assume "no traffic = no cost." That assumption is false for any resource that bills on provisioned capacity (Foundry Agents, Container Apps with `minReplicas ≥ 1`, PostgreSQL Flexible Server compute, Container Registry, Storage). The fix is structural, not behavioral — defaults in IaC + budget alerts catch this without depending on a human remembering to scale down. Operational thrift is a property of the infrastructure code, not a discipline expected of the operator.

Citation: `.squad/decisions/inbox/niobe-lesson-dormant-azure-cost.md`.

### 2. Observability is an operator-decision tool, not a single-metric dashboard

The initial framing was "cost visibility" — surface OpenAI spend per book so we know what each translation cost. Review converged on something larger: a four-column per-book operations dashboard surfacing cost, wall-time, validation status, and quality score side by side. The lesson is that operator dashboards are about *decision velocity*, not single-metric visibility. The operator's question after a run is "ship, re-run, or review?" and the dashboard must let them answer that in one glance — every signal needed for that decision belongs on the same surface. Citations: `.squad/decisions/inbox/niobe-observability-finops-framing.md`, `.squad/decisions/inbox/morpheus-observability-architecture.md`, `.squad/decisions/inbox/niobe-trinity-brief-phase1.md`.

### 3. Quality gates are first-class — count is 10, not 7, and they are addressed by name

Code has always had 10 gates in `src/transpose/pipeline/gates.py`; the docs described 7 because they pre-dated `operational_readiness_gate`, `export_rendering_gate`, and `source_output_comparison_gate`. The fix wasn't only to add the missing three — it was to drop the "Gate 1 / Gate 2 / …" numbering. Numbered enumeration in prose drifts every time a gate is added or reordered. Gates are now listed by function name in stage order, with code (`pipeline/gates.py`) as the source of truth. The lesson: when there's a list of named code-level objects, document them by name and link to the source; never by position. Citation: `.squad/decisions/inbox/niobe-scribe-gate-doc-drift.md`.

### 4. Quality scoring rejects same-family LLM-as-judge

The convenient option for translation quality scoring was to ask GPT-4o (the model that produced the translation) to grade its own output. We rejected it on rigour grounds: same-family judges exhibit measurable self-preference bias. The v1 quality score is layered: (A) multilingual embeddings for semantic similarity on every chunk, and (C) a cross-family LLM judge (Claude Sonnet 4.5) on a 5% stratified sample.[^layer-b] The lesson is that convenience of an already-integrated model is not a substitute for evaluation rigour — cross-family judges plus specialised embedding tooling produce better signal at lower cost than recycling the generation model to grade itself. Citation: `.squad/decisions/inbox/niobe-oracle-quality-score-brief.md`.

[^layer-b]: Layer B (reference-free MT QE, COMET-Kiwi class) was scoped out of v1 per Oracle's final spec (commit `404a439`) and deferred to v1.1.

### 5. Phase 2 cost optimization (#95) is quality-gated, not deferred

Cost levers are not fungible. Prompt caching is always-on because it carries no quality risk. Larger chunks and Document Intelligence tier downgrades require an Oracle A/B per book — the quality impact depends on the material. The GPT-4o → GPT-4o-mini swap was rejected outright for literary content because the smaller model loses the register and cultural-term handling that justify the whole pipeline. The lesson: every cost lever has a different quality blast radius. Treat them individually, attach each to a quality gate or A/B, and never bundle them as a single "save money" toggle. Citation: `.squad/decisions/inbox/niobe-backlog-prioritization.md`.

### 6. Performance work is sequenced behind observability, not deferred

An earlier framing argued throughput was the only metric that mattered, so wall-time optimisation could wait. The correction: a 10-hour wall time prevents same-day operator iteration regardless of throughput. Observability ships first so that subsequent performance cuts are surgical and data-driven rather than speculative. The lesson: "throughput is the only metric" misses the operator-feedback loop; latency matters even at low volume because it gates the iteration speed of the humans driving the system. Citations: `.squad/decisions/inbox/niobe-priority-ladder-2026-05-22.md`, `.squad/decisions/inbox/trinity-parallelism-investigation.md`.
