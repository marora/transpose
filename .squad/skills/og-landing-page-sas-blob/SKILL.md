---
name: "og-landing-page-sas-blob"
description: "Generate a static HTML landing page with OpenGraph meta tags that gates SAS-protected blob assets, enabling WhatsApp/iMessage/Signal link previews for private cloud files"
domain: "azure-storage, sharing, social-preview"
confidence: "high"
source: "earned — Transpose project Shape A share-URL design, 2026-05-20"
---

## Context

Azure Blob Storage private containers expose files via SAS (Shared Access Signature) URLs. These URLs work for direct downloads but **do not produce WhatsApp/iMessage/Signal link previews** because:
- Social scrapers fetch the URL and parse `<meta property="og:*">` tags from an HTML response.
- A SAS URL pointing to a PDF returns `Content-Type: application/pdf` (binary). Scrapers either show the filename or nothing.

This skill describes the pattern for generating a static HTML landing page per asset that:
1. Serves OG meta tags for social preview (title, description, image).
2. Links to SAS-protected blob assets (PDF, audio, etc.) without exposing them directly.
3. Lives on Azure Static Website (same storage account, zero extra infra).
4. Scales from private-share (Shape A) to public archive (Shape B) by swapping SAS links for public links when ready.

## Pattern

### Storage Layout

```
# Private container (book-workspaces): holds actual assets
book-workspaces/{slug}--{id}/input/source.pdf       ← private, SAS only
book-workspaces/{slug}--{id}/output/translated.pdf  ← private, SAS only

# Public Static Website container ($web): holds landing page HTML only
$web/{slug}--{id}/index.html                        ← public, no auth needed
$web/robots.txt                                     ← disallow indexing
```

### One-Time Storage Account Setup

```bash
# Enable Static Website on existing storage account
az storage blob service-properties update \
  --account-name {account} \
  --static-website \
  --index-document index.html \
  --auth-mode login

# Disallow search-engine indexing (does not affect WhatsApp/iMessage/Signal)
echo -e "User-agent: *\nDisallow: /" | az storage blob upload \
  --account-name {account} \
  --container-name '$web' \
  --name robots.txt \
  --data @- \
  --content-type "text/plain" \
  --auth-mode login
```

### Landing Page Template (Jinja2)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta property="og:type" content="{{ og_type | default('article') }}" />
  <meta property="og:title" content="{{ title }} — {{ author }}" />
  <meta property="og:description" content="{{ description | truncate(200) }}" />
  <meta property="og:url" content="{{ canonical_url }}" />
  {% if og_image_url %}
  <meta property="og:image" content="{{ og_image_url }}" />
  {% endif %}
  <meta property="og:site_name" content="{{ site_name }}" />
  <title>{{ title }} — {{ author }}</title>
</head>
<body>
  <h1>{{ title }}</h1>
  <p>{{ author }}</p>
  <p>{{ description }}</p>
  {% for asset in assets %}
  <a href="{{ asset.sas_url }}">{{ asset.label }}</a>
  {% endfor %}
</body>
</html>
```

### Generator (Python)

```python
from datetime import datetime, timedelta, timezone
from jinja2 import Template
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas

def generate_landing_page(
    account_name: str,
    account_key: str,     # or use DefaultAzureCredential
    slug_id: str,         # e.g. "vigyan-bhairav-tantra-vol-1--b7f3a2"
    metadata: dict,
    sas_expiry_days: int = 30,
) -> str:
    """
    Generates SAS URLs for assets, renders landing page HTML,
    uploads to $web container, returns the public landing page URL.
    """
    expiry = datetime.now(timezone.utc) + timedelta(days=sas_expiry_days)
    assets = []
    for asset in metadata["assets"]:
        sas = generate_blob_sas(
            account_name=account_name,
            container_name="book-workspaces",
            blob_name=f"{slug_id}/{asset['blob_path']}",
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )
        assets.append({
            "label": asset["label"],
            "sas_url": f"https://{account_name}.blob.core.windows.net/book-workspaces/{slug_id}/{asset['blob_path']}?{sas}",
        })

    template = Template(open("templates/landing.html.j2").read())
    static_url = f"https://{account_name}.z6.web.core.windows.net/{slug_id}/"
    html = template.render(
        title=metadata["title"],
        author=metadata["author"],
        description=metadata.get("translator_note", ""),
        canonical_url=static_url,
        og_image_url=metadata.get("cover_image_blob_url"),
        site_name="Transpose",
        assets=assets,
    )

    client = BlobServiceClient(f"https://{account_name}.blob.core.windows.net", credential=account_key)
    blob = client.get_blob_client("$web", f"{slug_id}/index.html")
    blob.upload_blob(html, overwrite=True, content_settings={"content_type": "text/html; charset=utf-8"})

    return static_url
```

## Privacy Posture

- **Landing page (`$web`):** Public — reachable by anyone with the URL. Contains only metadata (title, author, description). No binary content. Unguessable URL (UUID suffix) → security by obscurity, appropriate for friend-share.
- **Assets (private container):** SAS-only. Friends get read access to specific files for `sas_expiry_days`. SAS rotation replaces the links in the page on re-upload.
- **`robots.txt`:** Disallows web crawlers from indexing the landing page. WhatsApp/iMessage/Signal preview scrapers ignore `robots.txt` — they are link-preview fetchers, not indexers. This is the correct behaviour.

## Shape A → Shape B Promotion

When `license.status` flips to `verified-public-domain`:
1. Move/copy asset blob to public container or set blob-level public access.
2. Re-render landing page with public asset URLs instead of SAS URLs.
3. Landing page URL (canonical) is unchanged — bookmarks and shared links still work.
4. Optionally remove `robots.txt` disallow at this point to allow archive indexing.

## Anti-Patterns

- **Don't use SAS URL for the landing page itself.** The SAS query params in the URL do not break WhatsApp scraping, but they make the URL ugly, non-canonical, and expire. Serve the landing page as a public static file.
- **Don't put binary content on the landing page.** Embedding a PDF inline or as a data-URI defeats the privacy model.
- **Don't host the landing page on GitHub Pages if assets are on Azure.** Cross-origin complexity, and GitHub Pages is indexed by default. Static Website on the same storage account is simpler and keeps assets co-located.
- **Don't skip `og:title` and `og:description`.** These two tags are sufficient for WhatsApp/iMessage/Telegram preview. `og:image` is optional but improves preview quality significantly.
- **Don't rely on JavaScript for OG rendering.** Social scrapers do not execute JavaScript. OG tags must be in the raw HTML `<head>` on first response.

## References

- Azure Static Website docs: https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-static-website
- Azure Blob SAS: https://learn.microsoft.com/en-us/azure/storage/common/storage-sas-overview
- WhatsApp OG scraper behaviour: meta tag parsing, no JS execution, no robots.txt respect
