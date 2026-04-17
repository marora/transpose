### 2026-04-17T20:59:00Z: User directive — Serverless-first architecture
**By:** Mani (via Copilot)
**What:** Drop Redis entirely. Use PostgreSQL auto-pause (Flex Server) for near-zero idle cost. Keep Container Apps scale-to-zero. Pipeline runs infrequently — optimize for zero recurring cost when not in use. Replace Redis-backed pipeline state/locks with PostgreSQL equivalents.
**Why:** User request — pipeline runs infrequently, no value in always-on Redis/PostgreSQL costs. Captured for team memory.
