# Session Log: Open Questions Closed

**Timestamp:** 2026-05-20T23:10:06.050-04:00  
**Session:** Product & Architecture Alignment  
**Status:** ✅ COMPLETE

## Summary

Niobe + Morpheus locked all remaining Shape A open questions. Four product rules finalized. Full Azure storage architecture and landing-page strategy decided. All team handoffs clear.

## Decisions Locked

1. **Private-until-verified:** `claimed-public-domain` and `rights-unknown` books non-shareable via Shape A.
2. **`rights-unknown` mandatory default:** Hard constraint, four-layer enforcement (DB, app, metadata, tests).
3. **Share URL scope:** Both source + translated PDFs via 30-day read-only per-file SAS tokens.
4. **WhatsApp preview:** Option A (static landing pages on Azure Static Website). Shape A uses plain SAS URLs; preview feature bundled with Shape B.

## Firm Dates for Core Phase 1 Implementation

- Trinity: Enforce `rights-unknown`, metadata.json writer, landing-page generator
- Tank: Azure storage setup, DB migration (`license_status` + metadata columns), robots.txt
- Dozer: License constraint tests (5×), landing page tests (4×), schema validator

## Blockers Resolved

- Azure subscription: ✅ Active, no action needed
- Third-party PDF ownership: ✅ Acknowledged. `rights-unknown` default justified. No soft-risk assumption.
- Storage strategy: ✅ Blob from day one (private container + SAS). Hybrid with git for metadata.

## Next: Implement Phase 1

All three agents (Trinity, Tank, Dozer) have clear scope, acceptance criteria, and implementation artifacts. Scribe will track progress in orchestration log updates as each task completes.
