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
8. **Audiobook** (optional) — generates podcast-quality audio with neural TTS, LUFS-mastered MP3s, Podcast 2.0 RSS feed, read-along transcripts, and a consumer listen page
9. **Quality Gates** — 11 blocking checks across the pipeline validate OCR sanity, translation completeness, glossary integrity, document structure, artifact availability, golden-target QA, production readiness, source-output structural parity, audio quality, and operational readiness. See [docs/architecture.md](docs/architecture.md#quality-gates-pipelinegatespy) for the full catalog.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system design.
Admin dashboard auth is documented in [docs/auth.md](docs/auth.md).

## Stack

- **Runtime:** Python 3.12+
- **OCR:** Azure AI Document Intelligence
- **Translation:** Azure OpenAI GPT-4o
- **TTS:** Azure Speech Neural HD (configurable: ElevenLabs, OpenAI)
- **Audio mastering:** ffmpeg (LUFS normalization, compression)
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

A durable record of architectural decisions and the reasoning behind them — written for any reader, not only project insiders. The bullet-level changelog tells you what changed; this section exists so the *why* travels with the code. Entries are grouped by theme; the data anchoring each one (dollar figures, time windows, percentages) is project-empirical.

### Cost & operations

#### 1. Dormant cloud environments are not free — the fix is structural, not behavioral

A development resource group billed roughly **$436 over 28 dormant days** (≈ $15.60/day, projected ~$468/month) with zero application traffic, because several resource types bill for provisioned capacity rather than for invocations.

| Resource type | Idle $/day | Why it bills idle |
|---|---|---|
| Foundry / inference agent | $10.36 | Flat-rate provisioned 24/7 |
| Container App (`minReplicas ≥ 1`) | $3.97 | One always-on replica per default config |
| PostgreSQL Flexible Server | $0.66 | Compute always-on unless stopped |
| Storage / registry | <$0.50 | Capacity + flat SKU |
| Token-based LLM endpoint | $0.10 | Behaves correctly — no idle billing |

Over 90% of the burn came from two resources: the inference agent and the always-on container. The pattern is structural — per-day cost under real usage was the same or lower than during dormancy for those two resources, confirming they bill on provisioning, not traffic.

The fix is structural too. Defaults in infrastructure-as-code (`minReplicas: 0` for non-production container apps, agents declared under IaC lifecycle so teardown is one command) plus a low-threshold budget alert ($25/month on the dev resource group) catch dormant burn within days without depending on a human remembering to scale down. Operational thrift is a property of the infrastructure code, not a discipline expected of the operator.

#### 2. Summary tables are not source of truth — reconstruct from primary records

A per-book cost summary table originally treated as the canonical cost record turned out to contain only the final blob-write summary on a 10h+ pipeline run — missing ~99% of the actual spend, which lived in the underlying translation, page, and book records. The persistence helper only fired on the happy path after the final stage; failed, interrupted, and resumed runs left the summary partial or empty.

A summary table is a convenience, never an audit trail. For cost forensics, reconstruct from the primary records that capture each unit of work (per-call token usage, per-page operations). Persist summary rows on every terminal state — success, failure, resume — but treat the primary records as the source of truth.

### Quality & evaluation

#### 3. Same-family LLM-as-judge introduces measurable self-preference bias

Asking the model that produced an output to grade its own output is convenient and wrong. Same-family judges exhibit measurable self-preference bias — a well-documented evaluation failure mode. The remedy is a layered architecture: cheap multilingual-embedding similarity on every output (catches meaning drift), and a cross-family LLM judge on a stratified sample (rates literary or domain-specific dimensions deterministic tools can't reach). Convenience of an already-integrated model is not a substitute for evaluation rigor; cross-family judges plus specialized tooling produce better signal at lower cost than recycling the generation model to grade itself.

#### 4. Quality gates are calibrated against real corpora, not synthetic fixtures

A quality gate is finished when it does NOT fire on well-formed real-world content, not when it fires on the bug pattern. Repeated cover art on legitimate pages triggered an "image repetition" gate; OCR-degraded text mixed with Unicode replacement characters survived to a downstream writer because the gate checked input but not output. Both classes of failure are fixed by maintaining a real-corpus fixture set alongside the synthetic one and requiring both to pass.

Before shipping any numeric threshold, ask: *can this exact pattern appear in a legitimate input?* If yes, the threshold needs narrowing.

#### 5. Cost levers are not fungible — each has a different quality blast radius

Cost optimization is not a single "save money" toggle. Prompt caching is always-on because it carries no quality risk. Larger chunk sizes and lower-tier OCR require per-input A/B because the quality impact depends on the material. Swapping the primary translation model for a smaller variant was rejected outright for literary content because the smaller model loses register and cultural-term handling that justify the entire pipeline. Treat cost levers individually, attach each to a quality gate or A/B, and never bundle them.

#### 6. Content-filter false positives are handled by graduated fallback, not bypass

Commercial-LLM content filters false-positive on classical religious and philosophical text — body/energy/union terminology overlaps with patterns the filters were trained to flag. Roughly 2–3% of chunks trigger on this corpus.

The fix is a four-stage graduated escalation: (1) prepend scholarly context to the system prompt, (2) add publisher/discipline framing, (3) replace trigger terms with clinical placeholders, (4) fall back to sentence-level filtering with scholarly paraphrase of individual triggering sentences. Each stage runs only if the previous failed. Disabling or bypassing the filter outright is rejected — the filter is doing its job; the prompt is the variable.

When a safety filter false-positives on legitimate content, the answer is contextual reframing, not bypass. Build a graduated chain so most cases resolve at the cheapest stage.

### Documentation & process

#### 7. Operator dashboards optimize for decision velocity, not single-metric visibility

Initial framing for a per-book observability surface was "cost visibility" — surface translation spend so it's known. The framing converged on something larger: a per-book operations table surfacing cost, wall-time, validation status, and quality score side by side. The operator's question after a run is "ship, re-run, or review?" and the dashboard must let them answer that in one glance. Every signal needed for the decision belongs on the same surface.

#### 8. Document lists of code-level objects by name and link to source — never by position

Project documentation drifted from describing 7 quality gates to describing the same gates as 10 over time because the prose enumerated them as "Gate 1 / Gate 2 / …" while the code source-of-truth grew. Numbered enumeration in prose drifts every time the underlying list is reordered or extended. For any list of named code-level objects (gates, hooks, middleware, signals), document by function name in stage order and link to the source file. Code is the source of truth; prose tracks it by name.

#### 9. Latency matters even at low volume — observability sequences before performance

A natural framing argued throughput was the only meaningful metric because volume was low, so wall-time optimization could wait. A 10-hour pipeline runtime invalidated that: latency gates same-day operator iteration regardless of throughput. Observability ships first so subsequent performance cuts are surgical and data-driven rather than speculative. "Throughput is the only metric" misses the operator-feedback loop; latency matters even at low volume because it gates the iteration speed of the humans driving the system.

### Architecture & publishing

#### 10. Provenance artifacts ship with the published work

For any derivative work published openly — translations, transcriptions, restorations, annotations — the source artifact ships alongside the derivative on the same public surface. The reader must be able to verify the derivative against the source without asking for special access. Concretely: a public-domain translation publishes the original scan at `{landing}/source.pdf` next to the translated `{landing}/translated.pdf`. Provenance is a reader-facing contract, not an internal-only record.

#### 11. Publishing is a pipeline stage, not an external step

If a step is required for the work to be useful to its consumer, it belongs in the pipeline's dependency graph. Treating publishing (writing the artifact + landing page to public storage) as a post-pipeline manual script produced two recurring failures: landing pages shipped with broken links because the upload ran independently of the pipeline's success state, and resume-from-failure couldn't restore the published artifact because the publisher had no model of what the pipeline produced.

Pull consumer-facing steps into the pipeline as explicit stages, validated by the same surface as upstream work. Mark them non-fatal if their failure shouldn't lose upstream output — but keep them in the graph so they participate in resume, validation, and observability.
