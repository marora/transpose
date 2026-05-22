# Oracle — Publisher/Editor History

## Core Context
- **Project:** Transpose — agentic pipeline translating scanned Hindi/Punjabi PDF books into English
- **Stack:** Python, PostgreSQL, Redis, Azure Container Apps, Azure AI Document Intelligence, Azure OpenAI GPT-4o
- **Owner:** Manish
- **Previous incarnation:** Irulan (Dune cast) — see .squad/agents/_alumni/irulan/history.md for accumulated knowledge

## Learnings
(Recast from Irulan — Matrix universe. All prior knowledge preserved in alumni archive.)

### 2026-05-22: Translation Quality Score v1 Design Decisions

- **Judge model choice (Claude Sonnet 4.5):** Selected over Opus 4.6 (5× cost, marginal quality gain for 15-chunk samples) and Gemini Pro (inconsistent rubric adherence, tends toward generous scoring without differentiation at the 75–100 range). The key criterion was cost-to-signal ratio on small samples — Sonnet's literary comprehension is sufficient for directional quality scoring; Opus would be justified only for full-book evaluation or publisher sign-off workflows.

- **Layer B (COMET-Kiwi) exclusion rationale:** Reference-free MT QE models are trained on news/web parallel corpora. Osho's spiritual/philosophical register — metaphorical, non-literal, intentionally poetic — is adversarial to their training distribution. They penalize intentional translation liberties. Revisit in v1.1 only if domain-adapted QE becomes available.

- **Weight distribution philosophy:** Tier 1 (structural) gets only 30% because it catches catastrophe but cannot distinguish mediocre from excellent. Within Tier 2, embeddings (Layer A) get 30% because cosine similarity confirms topical alignment but cannot assess literary quality. The LLM judge (Layer C) gets the lion's share (70% of Tier 2 = 49% of final) because it's the only signal capable of evaluating what a publisher actually cares about: fluency, register, voice.

- **5% stratified sampling:** Stratified by chapter position (opening 40%, midpoint 30%, random 30%) rather than pure random, because chapter openings carry disproportionate editorial signal (framing, voice-setting, key terminology introduction). 15 chunks for a 300-chunk book provides sufficient signal without exceeding $0.50/book.

- **Green threshold at 85 (not 90):** A perfect 100 is unreachable in practice — the judge will always find something imperfect in literary voice. Setting green at 90 would mean no book ever ships green, making the signal useless. 85 represents "publishable with at most light copyediting" in my editorial judgment.

- **Graceful degradation design:** Never fail the pipeline for scoring failures. Each layer's absence triggers reweighting with the remaining layers. Score metadata always annotates which layers contributed, so Manish can discount accordingly.
