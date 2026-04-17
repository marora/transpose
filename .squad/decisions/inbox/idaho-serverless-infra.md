### Idaho — Serverless infra pivot
**Date:** 2026-04-17
**What:** Removed Redis (cache.bicep), updated Key Vault (removed Redis secret), updated Container App (removed Redis env vars), updated docker-compose (removed Redis service). Added pipeline_state table to init-db.sql. PostgreSQL auto-stop noted (post-deployment CLI). Cost estimate updated: ~$0/mo idle.
**Why:** User directive — pipeline runs infrequently, drop always-on services to minimize recurring costs.
**Impact:** Chani must update cache.py to use PostgreSQL for pipeline state. Tests using fakeredis must be rewritten.
