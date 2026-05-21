# 2026-05-21 — Shiv Sutra Public Access Fix

**Reported by:** Manish

**Error:** `PublicAccessNotPermitted` on raw Azure Blob URL

**Root cause:** User was directed to private `output` container instead of public Static Website path

**Fix:** Published to `$web/shiv-sutra/` (images, PDF, EPUB, metadata)

**Working URL:** `https://transposebooks.z13.web.core.windows.net/shiv-sutra/`

**Prevention:** Wired `TRANSPOSE_BLOB_STATIC_WEBSITE_URL` through Container App IaC and setup scripts

**Follow-up:** Issue #91 filed for dead landing page links
