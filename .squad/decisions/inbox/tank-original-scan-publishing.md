## 2026-05-21T13:45:28.928-04:00: Original scan publishing on public slug pages

**Author:** Tank

### Decision
For public-domain books published on the Azure Static Website slug path, publish the original scan alongside the translation at:
- `$web/{slug}/source.pdf` — public original scan
- `$web/{slug}/Shiv_Sutra.pdf` / translated artifact(s) — public translation assets
- `$web/{slug}/index.html` — TR-3 landing page with **Download Translation** + **Original Scan** buttons

Use the same static-website security model as the translation assets. Do **not** point the reader-facing Original Scan button at a private container (`source-pdfs` or `book-workspaces`) unless intentionally using a SAS URL strategy.

### Why
The live `shiv-sutra/` page had been manually republished with only translation links, even though the original scan already existed privately at `book-workspaces/shiv-sutra--ee92a4/input/source.pdf`. Republishing the source scan to `$web/shiv-sutra/source.pdf` restored the reader-facing contract without weakening storage account security.

### Operational convention
Prefer `$web/{slug}/source.pdf` as the public original-scan filename. It matches existing workspace naming (`input/source.pdf`), keeps URLs predictable, and makes landing-page repair straightforward when backfilling public-domain books.
