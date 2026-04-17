### Chani — Serverless code pivot

**Date:** 2026-04-17

**What:** Replaced Redis-backed Cache class with PostgreSQL-backed PipelineState. Uses pipeline_state table for status tracking and pg_try_advisory_lock for distributed locks. Removed redis/fakeredis dependencies. Updated runner, context, settings, conftest, and all affected tests.

**Why:** User directive — drop Redis for serverless-first architecture. PostgreSQL handles both persistent state and pipeline coordination.

**Impact:** No interface change for pipeline stages — they still call ctx.state.set_pipeline_status() etc. Tests updated to mock PostgreSQL instead of Redis.
