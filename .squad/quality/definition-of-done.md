# Definition of Done

> Nothing is "done" until there is proof. Claims without artifacts are open items.

**Effective:** 2025-07-18
**Owner:** Stilgar (Lead/Architect)
**Enforcement:** CI gates + PR review

---

## Completion Criteria

A work item (issue, PR, task) is **done** only when ALL of the following are true:

### 1. Artifact Generation
- [ ] PDF artifact is generated from the pipeline output
- [ ] ePub artifact is generated from the pipeline output
- [ ] Both artifacts are non-zero size and structurally valid

### 2. Artifact Publication
- [ ] PDF is uploaded to blob storage (or configured artifact store)
- [ ] ePub is uploaded to blob storage (or configured artifact store)
- [ ] Both have stable, publicly accessible download links
- [ ] Links are verified reachable (HTTP 200, correct Content-Type)

### 3. Validation Report
- [ ] Quality gate validation report is generated (machine-readable JSON)
- [ ] Report is attached to the PR or linked in the issue
- [ ] Report covers ALL five quality gates (see `gates.md`)

### 4. Quality Gates Pass
- [ ] **OCR Sanity** — PASS
- [ ] **Translation Completeness** — PASS
- [ ] **Glossary Integrity** — PASS
- [ ] **Document Structure** — PASS
- [ ] **Artifact Availability** — PASS

### 5. Review
- [ ] PR has at least one approving review
- [ ] No unresolved review threads
- [ ] CI pipeline is green (all gates pass)

---

## What "Done" Is NOT

- "It works on my machine" — not done
- "Tests pass but I didn't generate artifacts" — not done
- "Artifacts exist but no validation report" — not done
- "Gates pass but artifacts aren't published" — not done
- "Published but links are broken" — not done

---

## Exceptions

None. If a gate cannot run (e.g., no source document available), the work item stays open with a `blocked` label and a comment explaining why.
