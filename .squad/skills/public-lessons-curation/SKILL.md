---
name: "public-lessons-curation"
description: "Keep the README Architectural Progression / Lessons Learned section accessible to readers outside the project as new lessons land"
domain: "documentation, public-facing-writing, knowledge-curation"
confidence: "high"
source: "earned — Transpose lessons-section revamp 2026-05-22, after Manish flagged the original section as too internal for a public repo"
---

## Context

The repository's README contains an "Architectural Progression / Lessons Learned" section that captures the *why* behind architectural decisions. Decisions originate in internal decision packets under `.squad/decisions/inbox/` and `.squad/decisions.md`. The risk is that internal packets carry insider context — file paths under `.squad/*`, internal agent names, internal step/rung references, bare issue numbers, internal commit SHAs — and that context leaks into the public README unless the promotion step is explicit about stripping it.

This skill is consulted whenever a decision packet is being merged that contains material flagged as a transferable lesson (vs a task assignment, scope decision, or other internal decision).

## The promotion test

A lesson promotes to the public README only if it passes this single question:

> **Would a reader who has never seen this codebase take a usable lesson from this entry?**

If no, the lesson stays in `.squad/decisions/*` and is not promoted. If yes, the lesson is reformulated under the voice and structure rules below and lands in the README.

When uncertain, the default is *do not promote*. Author re-frames and tries again. It's better to omit a lesson than to publish one that reads as internal jargon.

## Voice rules

| Rule | Reason |
|---|---|
| **Impersonal-imperative voice.** No "we", "our", "I". | Lessons are claims about the world, not autobiographical notes. |
| **No `.squad/*` citations.** | Meaningless to external readers; visible internal-tooling artifact. |
| **No squad agent names** (e.g., role names from `.squad/team.md`). | Reads as proprietary jargon. |
| **No internal step/rung references** ("Step 1.5a", "Phase 1b"). | Internal sequencing; readers have no map. |
| **No bare GitHub issue numbers.** If issue context is essential, summarize it inline; otherwise omit. | "#97" is meaningless without context. |
| **No internal commit SHAs.** Cite the code path (`src/...`, `infra/...`) which is navigable. | Code paths survive history; SHAs are noise. |
| **Vendor and product names are fine.** (Azure, GPT-4o, Claude Sonnet, COMET-Kiwi, etc.) | Externally citable; help readers locate the technology. |
| **Cite external sources where they exist** (RFCs, vendor docs, papers, well-known patterns). | Anchors the lesson in shared knowledge. |
| **Keep empirical data** (dollar figures, percentages, time windows, tables). | This is the credibility anchor. Strip the framing, keep the numbers. |

## Structure rules

- The section is grouped into **four themes**, in this order: **Cost & operations**, **Quality & evaluation**, **Documentation & process**, **Architecture & publishing**. New lessons land in the most-fitting theme; never as ungrouped entries.
- Each lesson is an H4 (`####`) entry under its theme's H3 (`###`). The H2 (`##`) is the section header.
- Entry titles are short claims (10 words or fewer), declarative, no project name. Good: *"Same-family LLM-as-judge introduces measurable self-preference bias"*. Bad: *"Quality scoring rejects same-family LLM-as-judge"*.
- Entry body is 2–4 short paragraphs OR a short prose paragraph plus a small table when data lives best in a table. No more than ~150 words per entry unless data demands it.

## When this skill is consulted

- When merging any decision packet flagged as containing a transferable lesson.
- When a maintainer asks "does this belong in the public README?" about any piece of internal documentation.
- When reviewing a pull request that touches the README's lessons section.

## Who promotes vs who curates

- **Authoring** a public-facing lesson is the responsibility of whoever owns the decision (typically the PM-equivalent role in this team's structure). Authoring includes applying the voice and structure rules in this skill.
- **Curating** — merging the authored lesson into the README, deduplicating against existing entries, reordering within a theme if needed — is the responsibility of the session-logger/memory-manager role.
- If a decision packet contains lesson material but is written in internal voice, the curator does NOT silently rewrite it. The curator flags it back to the author for reformulation. Silent rewriting breaks the convention that the inbox packet is the canonical record.

## Anti-patterns

- **Promoting a task assignment as a lesson.** Task assignments ("agent X should do Y") are internal; lessons are claims about the world. Test: strip the named-actor and the imperative — is anything left? If no, it's a task, not a lesson.
- **Padding lessons with internal context to justify them.** If a lesson needs "we discovered X during phase Y of project Z" to make sense, it's not transferable; rework or omit.
- **Keeping `.squad/*` citations "for traceability."** Internal traceability lives in `.squad/decisions.md`; the README is the public-facing curated narrative. Don't conflate the two.
- **Splitting one lesson across multiple themes.** A lesson belongs in exactly one theme. If it genuinely spans two, the framing is too broad — split it into two distinct lessons or narrow it.
