# CI Gate Enforcement

> Gates are not suggestions. They are blocking checks enforced by CI.

**Effective:** 2025-07-18
**Owner:** Thufir (Quality Gate Owner) + Idaho (CI Infrastructure)

---

## PR Requirements

Every pull request targeting `main` must satisfy ALL of the following before merge is allowed:

### 1. Gate Execution
- All 5 quality gates run automatically on every PR
- Gates run against the PR's head commit (not base)
- Gate execution is triggered by CI pipeline (GitHub Actions or equivalent)
- Gates run in order: OCR Sanity → Translation Completeness → Glossary Integrity → Document Structure → Artifact Availability
- First failure halts remaining gates (fail-fast)

### 2. PR Bot Comment
The CI bot must post a comment on every PR with:

```
## 📋 Transpose Quality Report

**Run ID:** `{run_id}`
**Book:** `{book_title}` (`{book_id}`)

### Artifacts
- 📕 PDF: [Download]({pdf_link}) ({pdf_size})
- 📗 ePub: [Download]({epub_link}) ({epub_size})

### Validation Report
- 📊 [Full Report]({report_link})

### Quality Gates
| Gate | Status | Details |
|------|--------|---------|
| OCR Sanity | ✅ PASS / ❌ FAIL | {summary} |
| Translation Completeness | ✅ PASS / ❌ FAIL | {summary} |
| Glossary Integrity | ✅ PASS / ❌ FAIL | {summary} |
| Document Structure | ✅ PASS / ❌ FAIL | {summary} |
| Artifact Availability | ✅ PASS / ❌ FAIL | {summary} |

**Overall: ✅ ALL GATES PASS / ❌ BLOCKED — {N} gate(s) failed**
```

### 3. Merge Block
- If ANY gate fails → PR merge is blocked (GitHub branch protection rule)
- PR status check name: `transpose/quality-gates`
- Status check is **required** — cannot be bypassed without admin override
- Admin override requires a comment explaining the bypass reason

### 4. Machine-Readable Results
- Gate results are written to `validation-report.json` (see `gates.md` for schema)
- Report is uploaded as a CI artifact on every run
- Report is also posted to the PR as a downloadable link
- JSON schema enables downstream automation (dashboards, trend tracking, alerting)

---

## CI Pipeline Structure

```yaml
# Conceptual pipeline structure (actual implementation in CI config)

quality-gates:
  stage: test
  steps:
    - name: Run pipeline with test document
      run: python -m transpose.cli translate --input test-fixtures/sample.pdf

    - name: Run quality gates
      run: python -m transpose.quality.validate --output validation-report.json

    - name: Upload validation report
      uses: actions/upload-artifact@v4
      with:
        name: validation-report
        path: validation-report.json

    - name: Upload artifacts
      uses: actions/upload-artifact@v4
      with:
        name: book-artifacts
        path: output/*.{pdf,epub}

    - name: Post PR comment
      run: python -m transpose.quality.pr_comment --report validation-report.json
```

---

## Gate Failure Protocol

When a gate fails:

1. **CI marks PR as failed** — merge blocked automatically
2. **Bot posts failure details** — which gate, what failed, specific block/term IDs
3. **Assignee investigates** — uses validation report to pinpoint the issue
4. **Fix pushed** — gates re-run automatically on new commit
5. **If gate is flaky** — Thufir investigates threshold/criteria, proposes adjustment via decision record

---

## Monitoring

- Gate pass/fail rates tracked over time (Application Insights custom metrics)
- Metric: `transpose.quality.gate.{gate_name}.result` with dimensions `status=PASS|FAIL`
- Alert if any gate fails >3 times in a rolling 7-day window (indicates systemic issue)
