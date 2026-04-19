# Quality Ownership Model

> Every quality concern has exactly one owner. No shared ownership, no ambiguity.

**Effective:** 2025-07-18
**Author:** Stilgar (Lead/Architect)

---

## Ownership Assignments

| Role | Owner | Authority | Scope |
|------|-------|-----------|-------|
| **Quality Gate Owner** | Thufir (Tester) | Can block PRs if any gate fails. Has final say on whether quality criteria are met. Owns gate definitions, thresholds, and test coverage. | All 5 quality gates, validation report accuracy, test suite health |
| **Release/Artifact Owner** | Idaho (Cloud/Infra) | Ensures the publishing pipeline works end-to-end. Owns artifact upload, stable link generation, and download verification. If artifacts are broken, it's on Idaho. | Blob storage upload, CDN/link stability, artifact integrity checks, Artifact Availability gate infrastructure |
| **Observability/SRE** | Idaho (Cloud/Infra) | Owns logging, monitoring, alerting, and failure visibility. Pipeline failures must be visible within 5 minutes. Maintains the runbook. | Application Insights, Log Analytics, alert rules, runbook (`docs/runbook.md`), pipeline failure notifications |
| **Security/Secrets** | Idaho (Cloud/Infra) | Owns secrets hygiene, credential rotation, and ensuring zero secrets in code. Reviews all infra PRs for secret leaks. | Key Vault, Managed Identity config, credential rotation schedule, secret scanning |
| **Architecture** | Stilgar (Lead/Architect) | Owns system architecture, stage contracts, and cross-cutting technical decisions. Reviews all PRs for architectural compliance. | `docs/architecture.md`, `docs/api-contracts.md`, pipeline stage boundaries, service wrapper pattern |
| **Pipeline Implementation** | Chani (Developer) | Owns pipeline stage code. Responsible for stage correctness, contract compliance, and performance. | `src/transpose/pipeline/`, `src/transpose/services/`, stage-level bug fixes |

---

## Escalation Path

1. **Gate failure on PR** → Thufir reviews, comments with specifics, blocks merge
2. **Artifact/infra failure** → Idaho investigates, posts root cause within 24h
3. **Architecture dispute** → Stilgar decides, records in `.squad/decisions.md`
4. **Cross-cutting issue** → Stilgar triages and assigns to appropriate owner
5. **Unresolved disagreement** → Manish (project owner) has final call

---

## Accountability

- Each owner is responsible for **proactively** monitoring their domain, not just reacting to failures.
- Gate failures that persist across 2+ PRs trigger a root cause analysis led by the gate owner.
- Artifact link rot is checked weekly by Idaho (automated or manual).
- Security review happens on every infra PR — no exceptions.
