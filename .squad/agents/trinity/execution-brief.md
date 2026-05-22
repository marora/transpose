# Trinity Execution Brief — 2026-05-21T23:30:27-04:00

**From:** Niobe (via Scribe)

## Your Work Items (Strict Sequence)

**#97 (SECOND — BLOCKER):** Append-only cost_events table + runner instrumentation
- Estimated: 4–6h
- Depends on: #98 (Tank) must ship first
- Closes #93 (cost loss on failure)
- **Unblocks:** #99 (dashboard API)

**#99 (FOURTH — BLOCKER):** Dashboard API routes + projector (stage breakdown, cost estimates)
- Estimated: 6–8h
- Depends on: #97 done
- Delivers: Manish can query `/admin/api/cost/book-id` in <1 min
- **Unblocks:** #100 (dashboard frontend)

**#100 (FIFTH — BLOCKER):** Admin dashboard frontend (static HTML + simple JS)
- Estimated: 2–4h
- Depends on: #99 done
- Delivers: Manish sees dashboard with book list + cost breakdown
- **Completes observability v1**

## Critical Constraint

Do NOT start #99 until #97 is complete. Do NOT start #100 until #99 ships. Sequential dependencies are hard blockers.

## Timeline

- #97: start when Tank's #98 ships (target end-of-session-1)
- #99: start when #97 complete (target start-of-session-2)
- #100: start when #99 complete (target mid-session-2)
- **Target observability ship:** 2026-05-24 EOD

---

**Full doc:** `.squad/decisions/inbox/niobe-backlog-prioritization.md`
