"""BookWorkspace — per-book Azure Blob Storage workspace abstraction.

Manages artifact uploads, metadata.json lifecycle, SAS URL generation,
and landing page publishing for each translated book.

Layer 3 of the 4-layer rights-unknown enforcement lives here:
  - build_metadata() never accepts a license_status parameter — always writes
    'rights-unknown' and asserts it before returning.
  - write_metadata() hard-asserts license.status == 'rights-unknown' on upload.
  - update_metadata() raises if any caller attempts to write 'license' keys,
    enforcing the "do not auto-claim PD" rule: no pipeline stage may upgrade
    license.status; only an explicit, separate operator action may.

Blob path layout (per .squad/decisions.md "Architecture Addendum"):

  book-workspaces/
    {slug}--{short_id}/
      input/
        source.pdf
      output/
        translated.pdf
      landing/
        index.html          ← private workspace copy
      metadata.json

  $web/
    {slug}--{short_id}/
      index.html            ← public landing page (Azure Static Website)
"""

from __future__ import annotations

import html
import json
import os
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from transpose.services.azure_rbac_retry import with_rbac_retry

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

RIGHTS_UNKNOWN = "rights-unknown"

_LICENSE_STATUS_ENUM: frozenset[str] = frozenset([
    "rights-unknown",
    "claimed-public-domain",
    "verified-public-domain",
    "rights-cleared",
])

WORKSPACE_CONTAINER = "book-workspaces"
STATIC_WEBSITE_CONTAINER = "$web"

# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────


class RightsUnknownViolation(ValueError):  # noqa: N818 - existing decision-log term
    """Raised when any code path sets license.status to something other than
    'rights-unknown' at workspace creation time."""


class PipelineLicenseUpgradeGuard(RuntimeError):  # noqa: N818 - existing decision-log term
    """Raised when pipeline code attempts to modify license.status.

    License upgrades are a deliberate, out-of-band operator action.
    No pipeline stage may trigger them.
    """


# ──────────────────────────────────────────────
# Slug / prefix helpers
# ──────────────────────────────────────────────


def make_slug(title: str, max_chars: int = 40) -> str:
    """Convert a book title to a kebab-case ASCII slug ≤ max_chars characters.

    Examples:
        "Vigyan Bhairav Tantra Vol. 1" → "vigyan-bhairav-tantra-vol-1"
        "विज्ञान भैरव तंत्र"            → "vigyan-bhairav-tantra" (NFKD-normalised)
    """
    text = unicodedata.normalize("NFKD", title)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    slug = text[:max_chars].rstrip("-")
    # Ensure we have something usable even for fully non-ASCII titles
    return slug or "book"


def make_blob_prefix(slug: str, book_id: str | UUID) -> str:
    """Build the workspace blob prefix: ``{slug}--{last-6-hex-of-book-id}``.

    The last 6 hex chars of the UUID provide collision-safety without being
    unwieldy in URLs.
    """
    short_id = str(book_id).replace("-", "")[-6:]
    return f"{slug}--{short_id}"


# ──────────────────────────────────────────────
# BookWorkspace
# ──────────────────────────────────────────────


class BookWorkspace:
    """Per-book workspace in Azure Blob Storage.

    Encapsulates all blob I/O for a single translated book — artifact upload,
    metadata.json round-trips, SAS URL generation, and landing page publishing.

    Usage (pipeline integration)::

        workspace = BookWorkspace(
            book_id=book.id,
            slug=make_slug(book.title),
            blob_client=ctx.blob,
            static_website_url=ctx.settings.blob_static_website_url,
        )
        await workspace.upload_source(source_pdf_bytes)
        await workspace.upload_translated(translated_pdf_bytes)
        meta = build_metadata(book_id=..., slug=..., title=..., ...)
        await workspace.write_metadata(meta)
        ...
    """

    def __init__(
        self,
        book_id: str | UUID,
        slug: str,
        blob_client,  # transpose.services.blob_client.BlobClient
        static_website_url: str,
    ) -> None:
        self.book_id = str(book_id)
        self.slug = slug
        self.blob_prefix = make_blob_prefix(slug, book_id)
        self._blob = blob_client
        self._static_website_url = static_website_url.rstrip("/")

    # ── Properties ──────────────────────────────────────

    @property
    def landing_page_url(self) -> str:
        """Landing page URL served by Azure Static Website or local fallback."""
        if self._static_website_url:
            return f"{self._static_website_url}/{self.blob_prefix}/"
        return self._blob.blob_uri(STATIC_WEBSITE_CONTAINER, f"{self.blob_prefix}/index.html")

    @property
    def source_blob_name(self) -> str:
        return f"{self.blob_prefix}/input/source.pdf"

    @property
    def translated_blob_name(self) -> str:
        return f"{self.blob_prefix}/output/translated.pdf"

    @property
    def metadata_blob_name(self) -> str:
        return f"{self.blob_prefix}/metadata.json"

    # ── Upload helpers ────────────────────────────────────

    async def upload_source(self, source: bytes | str | Path) -> str:
        """Upload the source (original scanned) PDF to the workspace.

        Accepts raw bytes or a local file path.
        Returns the blob URI.
        """
        data = source if isinstance(source, bytes) else Path(source).read_bytes()
        return await self._blob.upload_pdf(
            container=WORKSPACE_CONTAINER,
            blob_name=self.source_blob_name,
            data=data,
        )

    async def upload_translated(self, source: bytes | str | Path) -> str:
        """Upload the translated PDF to the workspace.

        Accepts raw bytes or a local file path.
        Returns the blob URI.
        """
        data = source if isinstance(source, bytes) else Path(source).read_bytes()
        return await self._blob.upload_pdf(
            container=WORKSPACE_CONTAINER,
            blob_name=self.translated_blob_name,
            data=data,
        )

    # ── metadata.json ────────────────────────────────────

    async def write_metadata(self, metadata_dict: dict) -> str:
        """Write metadata.json to the workspace. Returns blob URI.

        **HARD CONSTRAINT — Layer 3:**
        ``license.status`` MUST equal ``'rights-unknown'`` or this method raises
        ``RightsUnknownViolation``. Never catch and swallow this exception.
        """
        status = metadata_dict.get("license", {}).get("status", "")
        if status != RIGHTS_UNKNOWN:
            raise RightsUnknownViolation(
                f"HARD CONSTRAINT VIOLATED: metadata.json must be created with "
                f"license.status='rights-unknown'. Got: {status!r}. "
                "Workspace creation must never set any other license status value."
            )

        data = json.dumps(metadata_dict, indent=2, ensure_ascii=False).encode("utf-8")
        return await self._blob.upload_bytes(
            WORKSPACE_CONTAINER,
            self.metadata_blob_name,
            data,
            content_type="application/json; charset=utf-8",
        )

    async def update_metadata(self, updates: dict) -> str:
        """Merge ``updates`` into the existing metadata.json and re-upload.

        **DO NOT AUTO-CLAIM PD GUARD:**
        Raises ``PipelineLicenseUpgradeGuard`` if ``updates`` contains a
        ``'license'`` key. License upgrades must never happen inside the pipeline.
        Only a deliberate, out-of-band operator action may change license.status.

        Intended for writing ``share.*`` fields and ``landing_page_url`` after
        the workspace publish step.
        """
        if "license" in updates:
            raise PipelineLicenseUpgradeGuard(
                "DO NOT AUTO-CLAIM PD: Pipeline stages must never modify "
                "license.status. Only an explicit, separate operator action "
                "may upgrade license status. Remove 'license' from the updates dict."
            )

        # Load existing metadata
        try:
            existing_bytes = await self._blob.download_blob(
                container=WORKSPACE_CONTAINER,
                blob_name=self.metadata_blob_name,
            )
            existing = json.loads(existing_bytes.decode("utf-8"))
        except Exception:
            existing = {}

        _deep_merge(existing, updates)
        existing["updated_at"] = datetime.now(UTC).isoformat()

        data = json.dumps(existing, indent=2, ensure_ascii=False).encode("utf-8")
        return await self._blob.upload_bytes(
            WORKSPACE_CONTAINER,
            self.metadata_blob_name,
            data,
            content_type="application/json; charset=utf-8",
        )

    # ── SAS URL generation ───────────────────────────────

    async def generate_sas_url(self, blob_name: str, expiry_days: int = 30) -> str:
        """Generate a read-only per-file SAS URL for ``blob_name``.

        Scope: per-file (not per-prefix). Permissions: read only.
        Uses user delegation key (no storage account key required).
        """
        if self._blob.uses_local_storage:
            return self._blob.blob_uri(WORKSPACE_CONTAINER, blob_name)


        from azure.storage.blob import BlobSasPermissions, generate_blob_sas

        now = datetime.now(UTC)
        start = now - timedelta(minutes=5)   # small buffer for clock skew
        expiry = now + timedelta(days=expiry_days)

        async_client = await self._blob._get_client()
        udk = await with_rbac_retry(
            lambda: async_client.get_user_delegation_key(start, expiry),
            on_retry=self._blob._emit_rbac_retry,
        )

        account_name = self._blob._account_url.split("//")[1].split(".")[0]

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=WORKSPACE_CONTAINER,
            blob_name=blob_name,
            user_delegation_key=udk,
            permission=BlobSasPermissions(read=True),
            expiry=expiry,
        )

        return (
            f"https://{account_name}.blob.core.windows.net"
            f"/{WORKSPACE_CONTAINER}/{blob_name}?{sas_token}"
        )

    # ── Landing page ─────────────────────────────────────

    async def publish_landing_page(self, html_str: str) -> str:
        """Upload landing page HTML to both ``$web`` (public) and the workspace.

        Uploads:
        - ``$web/{prefix}/index.html``                     — public, served by Azure
        - ``book-workspaces/{prefix}/landing/index.html``  — private workspace copy

        Returns the public landing page URL.
        """
        html_bytes = html_str.encode("utf-8")
        content_type = "text/html; charset=utf-8"

        await self._blob.upload_bytes(
            STATIC_WEBSITE_CONTAINER,
            f"{self.blob_prefix}/index.html",
            html_bytes,
            content_type=content_type,
        )
        await self._blob.upload_bytes(
            WORKSPACE_CONTAINER,
            f"{self.blob_prefix}/landing/index.html",
            html_bytes,
            content_type=content_type,
        )

        return self.landing_page_url


# ──────────────────────────────────────────────
# metadata.json builder (TR-2)
# ──────────────────────────────────────────────

# 14-field schema (Section D, .squad/decisions.md "Architecture Addendum"):
#   title, author, source_language, target_language, page_count, slug,
#   translator_note, cover_image_blob_url, landing_page_url,
#   share.source_pdf_sas_url, share.translated_pdf_sas_url,
#   share.sas_expiry, share.generated_at, license.status
#
# Plus supporting fields from the 2026-05-20T22:52 workspace schema:
#   workspace_id, book_id, provenance.source, pipeline_version,
#   created_at, updated_at, published_at, artifact_manifest


def build_metadata(
    *,
    book_id: str | UUID,
    slug: str,
    title: str,
    author: str,
    source_language: str,
    target_language: str = "English",
    page_count: int,
    source_url: str | None = None,
    source_edition: str | None = None,
    source_acquired_at: str | None = None,
    source_notes: str | None = None,
    translator_note: str | None = None,
    cover_image_blob_url: str | None = None,
    pipeline_version: str = "1.0.0",
    created_at: str | None = None,
) -> dict:
    """Build a validated metadata.json dict for a new workspace.

    ``license.status`` is **always** ``'rights-unknown'`` — there is no parameter
    for it. This is Layer 3 of the 4-layer rights-unknown enforcement.

    ``translator_note`` resolution order:
      1. The ``translator_note`` argument (if non-empty).
      2. ``TRANSPOSE_TRANSLATOR_NOTE`` environment variable.
      3. Synthesized default: "{title} by {author}, translated from
         {source_language} to {target_language} by Transpose ({page_count} pages)."

    ``source_acquired_at`` defaults to the current UTC timestamp when not supplied
    (representing the ingest time as a proxy acquisition timestamp).
    """
    now_iso = datetime.now(UTC).isoformat()
    effective_created_at = created_at or now_iso

    # Translator note: arg → env var → synthesized default
    effective_note = translator_note or os.environ.get("TRANSPOSE_TRANSLATOR_NOTE", "")
    if not effective_note:
        effective_note = (
            f"{title} by {author}, translated from {source_language} "
            f"to {target_language} by Transpose ({page_count} pages)."
        )

    short_id = str(book_id).replace("-", "")[-6:]
    workspace_id = f"ws-{short_id}"

    metadata: dict = {
        "workspace_id": workspace_id,
        "book_id": str(book_id),
        "slug": slug,
        "title": title,
        "author": author,
        "source_language": source_language,
        "target_language": target_language,
        "page_count": page_count,
        "translator_note": effective_note,
        "cover_image_blob_url": cover_image_blob_url,
        "landing_page_url": None,       # populated at workspace publish step
        "share": {
            "source_pdf_sas_url": None,     # populated at workspace publish step
            "translated_pdf_sas_url": None,  # populated at workspace publish step
            "sas_expiry": None,
            "generated_at": None,
        },
        "license": {
            # IMMUTABLE at creation — no caller parameter for this field.
            "status": RIGHTS_UNKNOWN,
            "notes": None,
        },
        "provenance": {
            "source": {
                "url": source_url,
                "edition": source_edition,
                # Default to ingest time when not supplied
                "acquired_at": source_acquired_at or now_iso,
                "notes": source_notes,
            }
        },
        "pipeline_version": pipeline_version,
        "created_at": effective_created_at,
        "updated_at": now_iso,
        "published_at": None,
        "artifact_manifest": [],
    }

    # Final hard assertion — Layer 3 last line of defence in this function
    assert metadata["license"]["status"] == RIGHTS_UNKNOWN, (
        f"BUG IN build_metadata: license.status must always be 'rights-unknown'. "
        f"Found: {metadata['license']['status']!r}"
    )

    return metadata


def validate_metadata(metadata: dict) -> list[str]:
    """Validate a metadata dict against the mandatory-before-share schema.

    Returns a list of human-readable validation error strings.
    An empty list means the metadata is valid.
    """
    errors: list[str] = []

    mandatory_fields = [
        "title",
        "author",
        "source_language",
        "target_language",
        "page_count",
        "slug",
        "book_id",
    ]
    for field_name in mandatory_fields:
        value = metadata.get(field_name)
        if value is None or value == "" or value == 0:
            errors.append(f"Missing or empty mandatory field: '{field_name}'")

    # license.status must be a valid enum value
    status = metadata.get("license", {}).get("status", "")
    if status not in _LICENSE_STATUS_ENUM:
        errors.append(
            f"Invalid license.status: {status!r}. "
            f"Must be one of: {sorted(_LICENSE_STATUS_ENUM)}"
        )

    return errors


# ──────────────────────────────────────────────
# Landing page generator (TR-3)
# ──────────────────────────────────────────────

# Default OG image used when no per-book cover is available.
# This is a project-level fallback — override via TRANSPOSE_DEFAULT_OG_IMAGE env var.
_DEFAULT_OG_IMAGE = os.environ.get(
    "TRANSPOSE_DEFAULT_OG_IMAGE",
    "https://transposebooks.z6.web.core.windows.net/og-default.png",
)

_LANDING_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #f5f2ee;
  --card: #ffffff;
  --ink: #1c1917;
  --muted: #6b7280;
  --accent: #b45309;
  --accent-light: #fef3c7;
  --btn-primary: #1c1917;
  --btn-primary-text: #ffffff;
  --btn-secondary: #e7e5e4;
  --btn-secondary-text: #1c1917;
  --radius: 12px;
  --shadow: 0 4px 24px rgba(0,0,0,0.10), 0 1px 4px rgba(0,0,0,0.06);
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    sans-serif;
}

html { font-size: 16px; -webkit-text-size-adjust: 100%; }

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--ink);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 2rem 1rem 4rem;
}

.brand {
  font-size: 0.8rem;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 2rem;
  font-weight: 600;
}

.card {
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  max-width: 560px;
  width: 100%;
  padding: 2.5rem 2.5rem 2rem;
}

.badge {
  display: inline-block;
  background: var(--accent-light);
  color: var(--accent);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding: 0.25em 0.75em;
  border-radius: 999px;
  margin-bottom: 1.25rem;
}

h1 {
  font-size: clamp(1.5rem, 5vw, 2rem);
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--ink);
  margin-bottom: 0.5rem;
}

.author {
  font-size: 1rem;
  color: var(--muted);
  font-weight: 500;
  margin-bottom: 1.5rem;
}

.divider {
  width: 3rem;
  height: 3px;
  background: var(--accent);
  border-radius: 2px;
  margin-bottom: 1.5rem;
}

.description {
  font-size: 0.975rem;
  line-height: 1.7;
  color: #44403c;
  margin-bottom: 2rem;
}

.downloads {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.875rem 1.5rem;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 600;
  text-decoration: none;
  transition: opacity 0.15s ease, transform 0.1s ease;
  cursor: pointer;
}

.btn:hover { opacity: 0.88; transform: translateY(-1px); }
.btn:active { transform: translateY(0); }

.btn-primary {
  background: var(--btn-primary);
  color: var(--btn-primary-text);
}

.btn-secondary {
  background: var(--btn-secondary);
  color: var(--btn-secondary-text);
}

.btn-icon { font-size: 1.1em; }

footer {
  margin-top: 2rem;
  max-width: 560px;
  width: 100%;
  text-align: center;
  color: var(--muted);
  font-size: 0.825rem;
  line-height: 1.8;
}

footer a { color: var(--accent); text-decoration: none; }
footer a:hover { text-decoration: underline; }

@media (min-width: 600px) {
  .downloads { flex-direction: row; }
  .btn { flex: 1; }
}
"""

_LANDING_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">

  <!-- Open Graph -->
  <meta property="og:type" content="book" />
  <meta property="og:site_name" content="Transpose" />
  <meta property="og:title" content="{og_title}" />
  <meta property="og:description" content="{og_description}" />
  <meta property="og:url" content="{og_url}" />
  <meta property="og:image" content="{og_image}" />

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{og_title}" />
  <meta name="twitter:description" content="{og_description}" />
  <meta name="twitter:image" content="{og_image}" />

  <title>{page_title}</title>
  <style>{css}</style>
</head>
<body>
  <p class="brand">Transpose</p>

  <div class="card">
    <span class="badge">Translated Book</span>
    <h1>{title}</h1>
    <p class="author">{author}</p>
    <div class="divider" role="presentation"></div>
    <p class="description">{description}</p>

    <div class="downloads">
      <a class="btn btn-primary" href="{translated_url}" rel="noopener">
        <span class="btn-icon">&#8595;</span> Download Translation
      </a>
      <a class="btn btn-secondary" href="{source_url}" rel="noopener">
        <span class="btn-icon">&#8595;</span> Original Scan
      </a>
    </div>
  </div>

  <footer>
    <p>{source_lang}&nbsp;&rarr;&nbsp;{target_lang}&nbsp;&middot;&nbsp;{page_count}&nbsp;pages&nbsp;&middot;&nbsp;{translation_date}</p>
    <p>Translated by <a href="https://github.com/marora/transpose">Transpose</a></p>
  </footer>
</body>
</html>"""


def generate_landing_html(metadata: dict) -> str:
    """Generate the per-book landing page HTML from a metadata dict.

    Renders OpenGraph + Twitter Card meta tags, title, author, description,
    two download buttons (translated PDF + source scan), and a metadata footer.

    Per Manish's directive (.squad/decisions/inbox/copilot-directive-20260520-231930.md):
    optimised for "wow factor with early users" — clean typography, mobile-first,
    single-page, zero external dependencies (all CSS is inline).

    Does NOT reveal ``license.status`` — per Morpheus's Shape A decision,
    license status is an internal operational field, not a reader-facing surface.

    Args:
        metadata: A metadata dict as produced by ``build_metadata()``, optionally
            with ``share.*`` fields populated (SAS URLs).

    Returns:
        A complete UTF-8 HTML string ready for upload.
    """
    title = metadata.get("title", "Untitled")
    author = metadata.get("author", "Unknown Author")
    source_lang = metadata.get("source_language", "")
    target_lang = metadata.get("target_language", "English")
    page_count = metadata.get("page_count", 0)
    translator_note = metadata.get("translator_note", "") or ""
    cover_image = metadata.get("cover_image_blob_url") or _DEFAULT_OG_IMAGE
    landing_url = metadata.get("landing_page_url", "")

    share = metadata.get("share", {}) or {}
    translated_url = share.get("translated_pdf_sas_url") or "#"
    source_url = share.get("source_pdf_sas_url") or "#"
    generated_at_raw = share.get("generated_at") or metadata.get("updated_at", "")

    # Format the translation date for the footer (YYYY-MM-DD is enough)
    translation_date = generated_at_raw[:10] if generated_at_raw else "—"

    # OG description: translator_note or synthesized fallback (max 200 chars)
    description = translator_note
    if not description:
        description = (
            f"{title} by {author}, translated from {source_lang} "
            f"to {target_lang} by Transpose ({page_count} pages)."
        )
    og_description = description[:200]

    # HTML-escape all values that go into attribute contexts
    def esc(s: str) -> str:
        return html.escape(str(s), quote=True)

    og_title_str = f"{title} — {author}"

    return _LANDING_HTML.format(
        css=_LANDING_CSS,
        page_title=esc(og_title_str),
        og_title=esc(og_title_str),
        og_description=esc(og_description),
        og_url=esc(landing_url),
        og_image=esc(cover_image),
        title=esc(title),
        author=esc(author),
        description=esc(description),
        translated_url=esc(translated_url),
        source_url=esc(source_url),
        source_lang=esc(source_lang),
        target_lang=esc(target_lang),
        page_count=page_count,
        translation_date=esc(translation_date),
    )


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────


def _deep_merge(base: dict, updates: dict) -> dict:
    """Recursively merge ``updates`` into ``base`` in-place. Returns ``base``."""
    for key, value in updates.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
