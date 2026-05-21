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

**Three shapes identified:**
- Shape A (smallest): Personal translation tool. Workspace is local/private, archive is just artifact backup.
- Shape B (medium): Curated public archive site. Metadata index + free downloads. No audiobooks in MVP.
- Shape C (largest): Publishing platform. Multi-format (text/audio/glossary), review workflow, potential distribution.

**Recommendation:** Build workspace storage layer now (Morpheus's design works for all shapes). Defer archive UI, audiobook pipeline, and review workflow until Manish names the shape.

### 2026-05-20 (Afternoon): Manish Answered Q1 — Trajectory, Not Single Shape

**Manish's Q1 Answer (end readers):**
> "For now it will be only me or some close colleagues or friends I will share the URL with so they can access and download or view. But the longterm goal is to steadily build an archive / repository of rare never-translated PDFs from different parts of the world, for whoever is interested in gaining access to these."

**Key signals:**
1. **Trajectory, not shape:** Near-term is Shape A (personal + tight circle, URL-protected). Long-term is Shape B (public archive, open to whoever).
2. **Scope expansion:** "Rare never-translated PDFs from different parts of the world" — multilingual/global scope, not just Hindi/Punjabi heritage.
3. **Implicit near-term product decision:** Needs URL-protected private archive surface right now.
4. **Archive is discovery + access:** This is Shape B language (showcase), not Shape A language (lineage tracking).

**Strategic move:** Framing shifted from "pick one shape" to "enable the trajectory" — build Shape A now, keep Shape B reachable per-book.

### 2026-05-20 (Late): Manish Answered Q2 — Copyright Posture

**Manish's Q2 Answer (copyright/redistribution rights):**
> "I don't own the translation rights, I don't have explicit permission to redistribute, as I am looking at antiquated spiritual books, and my understanding is that these books' main purpose is to spread the wealth of information, IMHO they are generally considered public-domain work."

**The legal reality:**
- Source text (ancient Sanskrit/etc.): Likely genuinely public domain.
- Specific PDF edition: Modern publishers add commentary/typesetting/illustrations → fresh copyright (life+70).
- His translation: He owns it, but it's a derivative of the PDF. If the PDF is copyrighted, translation may be infringing.
- Jurisdiction matters: Public domain rules differ (India, US, UK, EU).

**PM move (Path 2 — structured future-proofing):** Don't gatekeep him now. Add two fields to workspace metadata per book: `license.status` (claimed-public-domain | verified-public-domain | rights-cleared | rights-unknown) and `provenance.source` (URL/edition of PDF scanned). For Shape A: any status fine. For Shape B: gate on verified-public-domain or rights-cleared only.

**Manish approved this framing.** It keeps him productive, preserves trajectory, and makes the workspace itself an audit trail for per-book public/private decisions.

### 2026-05-20 (Final): Product Brief Locked

**Scope finalized:**
- **Build now:** Shape A (personal workbench + private URL share)
- **Shape B (public archive):** Gated per-book, not corpus-wide, via license.status field
- **Copyright strategy:** Two metadata fields (license.status, provenance.source) track per-book judgment; public promotion deferred until status is verified/cleared
- **Deferred:** audiobook pipeline, formal review workflow, archive site UX, multi-channel distribution
- **Schema additions:** license{status, notes}, provenance{source, scanned_date, notes} baked into workspace metadata from day one

**Decision path:** Q1 → trajectory insight → Q2 → copyright risk → Path 2 (structured metadata, not gatekeeper) → Manish approval → final brief

**Key learning:** Manish prefers "structured field to make the decision explicit per book" over "I'll gatekeep you architecturally." This is the right posture — it gives him agency, keeps the vision alive, and makes the workspace itself the audit trail. Trust + transparency > control.

**Next:** Morpheus updates workspace schema, Trinity/Tank begin Phase 1 implementation.

### 2026-05-20 (Final): Four Open Questions Answered — Shape A Rules Locked

**Manish's final answers to the four open architecture questions:**

1. **`claimed-public-domain` visibility under Shape A:**
   > "Keep them fully private until I have upgraded them to verified-public-domain."
   
   **Move:** Private-until-verified is now a firm rule, not a soft default. No exception for friends-share with claimed status. Books must be `verified-public-domain` or `rights-cleared` to qualify for any Shape A private URL share.

2. **Azure subscription:**
   > "Active, already logged in."
   
   **Routing:** Morpheus/Tank handle technical setup. No product action.

3. **Share URL scope + WhatsApp preview bonus:**
   > "Both source PDF AND translated PDF. Bonus ask: When I share the URL via WhatsApp, can it also pull in a small 1-sentence title of the translated book and/or author?"
   
   **Move:** Share URLs include both PDFs. WhatsApp preview (OpenGraph metadata) is DEFERRED post-MVP — it's nice-to-have for close-friend sharing (friends already trust the link), but essential when Shape B (public archive + website) is designed. For MVP: plain SAS URLs satisfy the use case. For Phase 2: OpenGraph + preview wrapper can be built as part of archive UI.

4. **PDF ownership:**
   > "Third-party PDFs collected from the internet."
   
   **Move:** This is the hard-risk path. No chain of custody. Every book defaults to `rights-unknown` and stays there until Manish researches and upgrades per-book. This locks the design: `rights-unknown` is not a soft default — it's mandatory and enforced at workspace creation. Urgency of per-book license verification is now elevated.

**Resulting firm product rules:**
- **Private-until-verified:** `claimed-public-domain` and `rights-unknown` books are never shareable; only `verified-public-domain` and `rights-cleared` qualify for Shape A private URL.
- **`rights-unknown` is mandatory default:** Every new workspace defaults to this. Trinity must set it explicitly; Tank enforces it with CHECK constraint.
- **Deliberate license claim is per-book:** Upgrade from `rights-unknown` is a conscious per-book action, not a batch operation or shortcut.

**Team impacts:**
- **Trinity:** Workspace creation API must always set `license.status = 'rights-unknown'` explicitly.
- **Tank:** DB column + CHECK constraint + backfill for existing books; no change to Blob ACL/SAS setup.
- **Dozer:** Tests verify default is `rights-unknown`; verify promotion gate rejects `claimed-public-domain` and `rights-unknown`; verify only `verified-public-domain` and `rights-cleared` qualify for SAS URL generation.

**Key learning:** Manish's explicit "keep them private" answer closes a gap in the design. It's no longer a judgment call about whether claimed-PD is strict enough — it's a firm rule. Third-party internet PDFs + no chain of custody = always start with `rights-unknown` and research per-book. This is the right posture for copyright risk.

**Next:** No open questions remain. Phase 1 can proceed with full license-status rigor. Pause Shape B product framing until 3–5 books are live (3–4 weeks).

### 2026-05-21T04:39:36Z: Manish's Wow-Factor Directive — Landing Pages Ship from Day One

**The input:** Manish (via Copilot directive) — "Invest in polish (e.g., landing pages with OG previews from day one) that gets initial readers excited to read and provide feedback. Don't ship a bare-bones MVP when a small additional investment yields a much stronger first impression."

**Product context:** This overrides Niobe's earlier 2026-05-20 recommendation to defer WhatsApp preview + archive UI until Shape B (post-MVP). The directive prioritizes first-impression polish for early users over strict MVP minimalism.

**What happened:** Trinity built landing page generation (TR-3) with Open Graph + Twitter Card meta tags. Dozer's tests now assert Twitter Card presence. Landing pages are live as part of the workspace pipeline (Stage 8). Books will have public-but-unindexed landing pages at `https://transposebooks.z{n}.web.core.windows.net/{slug}--{book_id_short}/` from day one.

**Result:** Wow-factor achieved for Shape A private sharing. When Manish shares a book URL with friends via WhatsApp/iMessage/Slack, the landing page renders with OG preview (title, author, book cover, translator note, download links). This is a small build (static HTML, zero JS, zero external dependencies) but high-value signal for readers.

**Key learning:** User priorities can override initial MVP framing. Manish's judgment here is sound — early readers' first impression drives feedback quality and word-of-mouth. The polish is worth the small cost in time. PM should not gatekeep early user experience based on abstract "MVP" ideals.

**Next:** Shape B product framing can use the same landing page template as a foundation (expand metadata, add search index, add per-book review/feedback UI).


### 2026-05-20 (Evening): Manish Asks — GitHub Repo vs. Blob Storage for Shape A Artifacts

**Manish's question:** "Should this content be saved under the GitHub repo for the time being?"

**Product analysis (not architecture — Morpheus handles the architecture decision in parallel):**

The real question: "What's the right friction level for Shape A private sharing, given that every book starts with `license.status = rights-unknown`?"

**Three options and their product costs:**

1. **Public GitHub repo (raw file links)**
   - Friction: zero
   - Product cost: Makes every untranslated book world-readable + indexed by Google + archived by Wayback Machine before Manish verifies rights. Creates a de facto "public archive" by accident, contradicting his own "rights-unknown" caution. Cannot retract easily.

2. **Private GitHub repo + invite friends**
   - Friction: moderate-high
   - Product cost: Friends need GitHub accounts + accept invites. Shape A audience is "people with a link," not "GitHub collaborators."

3. **Azure Blob signed URLs (controlled access)**
   - Friction: low
   - Product benefit: Anyone with the link downloads; no account needed; URL can expire or be revoked. Preserves "rights-unknown" posture (not world-readable). Explicit opt-in path to Shape B later.

**Product recommendation: Use Blob signed URLs for Shape A; keep GitHub repo for code + metadata only.**

Why: Shape A is "private share with friends," not "public archive by accident." Starting with `license.status = rights-unknown` in a public GitHub repo collapses his Shape A → Shape B decision tree. Blob signed URLs give him control: translate → verify rights per-book → promote to Shape B archive when ready. This aligns with Morpheus's architecture (blob canonical, repo for code/metadata) and protects his own legal optionality.

**Summary:** Don't put untranslated books (license.status = rights-unknown) in public GitHub. Use blob signed URLs for Shape A private sharing; preserves his per-book public/private decision and prevents accidental public archive.

### 2026-05-21T12:17:57-04:00: Issue #91 — Dead download links on existing landing pages (Product-facing)

**Scope:** Product experience blocker

**Problem:** Existing landing pages (e.g., `$web/shiv-sutra--ee92a4/`) have blank download buttons because SAS generation failed during workspace publish. When Niobe runs Stage 8, if SAS generation fails silently, the published landing page becomes unusable.

**Decision:** Pipeline must validate SAS generation before publishing landing page with download buttons. If SAS generation fails, either:
1. Fail Stage 8 with clear error, or
2. Publish landing page with disabled/disabled download buttons + error message

**Ticket:** https://github.com/marora/transpose/issues/91

**Owner:** Trinity (pipeline fix)

### 2026-05-21T17:45:28Z: Shiv Sutra landing — both download buttons now visible

**Status:** Fixed

Tank diagnosed: Pipeline `source_url` threading is correct; manual republish in prior session omitted it from rendered HTML. Tank re-rendered landing.html with source_url properly threaded and copied source PDF to web root. Both buttons (translation + original scan) now showing on https://transposebooks.z14.web.core.windows.net/shiv-sutra/.

**Product impact:** Shape A private URL sharing now shows complete book packaging (both PDFs) as designed. Readers can access source + translation.

---

