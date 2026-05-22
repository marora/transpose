# Trinity drifted-code commit split — Issue #106

**Timestamp:** 2026-05-22T16:01:10-04:00
**Author:** Trinity
**Related:** #106

## PR 1 — feature code

Shipped in `squad/106-commit-drifted-code`:

- `src/transpose/services/azure_rbac_retry.py`
- `src/transpose/pipeline/workspace.py`
- `src/transpose/workspace/`
- `src/transpose/backfill_workspace.py`
- `src/transpose/templates/landing.html.j2`
- `scripts/backfill_workspace.py`
- `tests/golden/landing_page_fixture.html`
- `tests/unit/services/test_azure_rbac_retry.py`
- `tests/unit/workspace/`
- `tests/unit/pipeline/test_landing_page.py`
- `tests/unit/test_backfill_workspace.py`

Verification:

- `python -m ruff check` on PR 1 paths: passed
- `pytest tests/unit/services -q`: passed
- `pytest tests/unit/workspace -q`: passed
- `pytest tests/unit/pipeline -q`: passed

Coverage gap flagged in PR 1: no dedicated unit test for live Azure Blob upload/user-delegation SAS behavior in `BookWorkspace`; current coverage avoids external I/O.

## PR 2 — CI/squad scaffolding drift

Shipped in `squad/106-squad-infra-drift`:

- new squad workflow YAML files under `.github/workflows/squad-*.yml`
- new Copilot error-recovery skill under `.copilot/skills/error-recovery/`
- new squad Azure auth/dashboard skills under `.squad/skills/`
- `uv.lock`
- this handoff note and Trinity history update

## Deferred / deliberately excluded

- `output/` — build artifacts
- `osho-validation-report.json` — one-off output
- `*.Zone.Identifier` / endpoint DLP metadata — Windows/download metadata
- `docs/auth.md` — waiting on Manish posture decision in #107
- `infra/` — Tank-owned parallel work
- unrelated scripts/tests not listed in #106 PR scopes — left for owner triage
