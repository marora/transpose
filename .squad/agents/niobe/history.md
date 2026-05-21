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

## Learnings

### 2026-05-20: Initial Product Framing — Workspace/Archive/Audiobook Question

**Signal:** Manish's original request bundled three distinct product decisions together:
1. Workspace abstraction (storage + artifact management) — *technical debt relief*
2. Public archive of translated books — *new product shape*
3. Audiobook capability (future) — *distribution/accessibility expansion*

**Parsing his intent:** Manish wants to move from "one-off translates" toward a reusable platform that can handle multiple books, archive them in some coherent way, and eventually add audiobooks. He's not yet clear on *for whom* — personal collection, public showcase, or distribution platform.

**Key insight:** Morpheus's architecture answer (BookWorkspace abstraction + Blob storage) is correct *for any shape*. But scope of "archive" and "audiobook" are wildly different across shapes. Must frame product before building storage layer.

**Open uncertainties:**
- **Audience:** Personal tool for Manish? Public heritage books site? Publishing platform?
- **Archive intent:** Is this a private working backup, or a public discoverability asset?
- **Monetization:** Forever free, or exploring donations/paid download later?
- **Review/QA:** Single-person review (Manish), or external scholarly review workflow?
- **Audiobook priority:** Accessibility for Manish's own listening? Public distribution?

**Three shapes identified:**
- Shape A (smallest): Personal translation tool. Workspace is local/private, archive is just artifact backup.
- Shape B (medium): Curated public archive site. Metadata index + free downloads. No audiobooks in MVP.
- Shape C (largest): Publishing platform. Multi-format (text/audio/glossary), review workflow, potential distribution.

**Recommendation:** Build workspace storage layer now (Morpheus's design works for all shapes). Defer archive UI, audiobook pipeline, and review workflow until Manish names the shape. This is a gate, not a blocker.
