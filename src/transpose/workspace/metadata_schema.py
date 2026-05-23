"""Metadata schema validator for BookWorkspace metadata.json.

Validates the 14-field metadata.json spec defined in .squad/decisions.md
(2026-05-20T23:10:06 Architecture Addendum, Section D).

Every book workspace carries a metadata.json file.  Before the landing page
can be generated and SAS share URLs can be distributed, all
mandatory-before-share fields must be present and valid.

Usage::

    from transpose.workspace.metadata_schema import validate_metadata, MetadataValidationError

    try:
        validate_metadata(data_dict)
    except MetadataValidationError as exc:
        print(exc.errors)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Constants — derived directly from .squad/decisions.md
# ---------------------------------------------------------------------------

#: The four legal values for license.status.
#: Source: 2026-05-20T22:52:32 BookWorkspace schema extension decision.
LICENSE_STATUS_ENUM: frozenset[str] = frozenset(
    {
        "rights-unknown",
        "claimed-public-domain",
        "verified-public-domain",
        "rights-cleared",
    }
)

#: Statuses that qualify a book for public archive promotion (Shape B).
#: Books NOT in this set must remain workspace-private.
#: Source: Promotion-Eligibility Rule, same decision.
LICENSE_STATUS_PROMOTION_ELIGIBLE: frozenset[str] = frozenset(
    {
        "verified-public-domain",
        "rights-cleared",
    }
)

#: Default license status set at workspace creation.  Must never be changed at
#: ingest time — only via a deliberate per-book upgrade action.
LICENSE_STATUS_DEFAULT: str = "rights-unknown"

# SAS URL must contain the book-workspaces container path and be HTTPS.
# Pattern: https://<account>.blob.core.windows.net/book-workspaces/<prefix>/<path>?<sas-params>
_SAS_URL_RE = re.compile(
    r"^https://[a-z0-9]+\.blob\.core\.windows\.net/book-workspaces/.+\?.+$",
    re.IGNORECASE,
)

#: Specifically the source PDF SAS URL must point at input/source.pdf
_SOURCE_PDF_SAS_URL_RE = re.compile(
    r"^https://[a-z0-9]+\.blob\.core\.windows\.net/book-workspaces/.+/input/source\.pdf\?.+$",
    re.IGNORECASE,
)

#: Specifically the translated PDF SAS URL must point at output/translated.pdf
_TRANSLATED_PDF_SAS_URL_RE = re.compile(
    r"^https://[a-z0-9]+\.blob\.core\.windows\.net/book-workspaces/.+/output/translated\.pdf\?.+$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class MetadataValidationError(ValueError):
    """Raised when metadata.json fails schema validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_iso8601(value: Any) -> bool:
    """Return True when *value* is a non-empty ISO 8601 datetime string."""
    if not isinstance(value, str) or not value.strip():
        return False
    # Try the formats that appear in the spec examples
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%dT%H:%MZ",
    ):
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            pass
    # Also try fromisoformat (Python 3.7+ handles most variants)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        pass
    return False


def _get_nested(data: dict, *keys: str) -> Any:
    """Safely retrieve a nested key from a dict; return None if missing."""
    node: Any = data
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_metadata(data: dict) -> None:  # noqa: C901 – intentionally long for clarity
    """Validate *data* against the BookWorkspace metadata.json schema.

    Raises :class:`MetadataValidationError` listing every violation found.
    Returns ``None`` on success.

    Mandatory-before-share fields validated (source: decisions.md §D):
        title, author, source_language, target_language, page_count, slug,
        landing_page_url,
        share.source_pdf_sas_url, share.translated_pdf_sas_url,
        share.sas_expiry, share.generated_at,
        license.status, provenance.source.acquired_at
    """
    errors: list[str] = []

    # --- Simple string fields ---
    string_fields = (
        "title",
        "author",
        "source_language",
        "target_language",
        "slug",
        "landing_page_url",
    )
    for field in string_fields:
        val = data.get(field)
        if not val or not isinstance(val, str) or not val.strip():
            errors.append(f"Missing or empty required field: '{field}'")

    # --- page_count: positive integer ---
    page_count = data.get("page_count")
    if page_count is None:
        errors.append("Missing required field: 'page_count'")
    elif not isinstance(page_count, int) or page_count < 1:
        errors.append(f"'page_count' must be a positive integer, got: {page_count!r}")

    # --- license.status: must be in 4-value enum ---
    license_status = _get_nested(data, "license", "status")
    if license_status is None:
        errors.append("Missing required field: 'license.status'")
    elif license_status not in LICENSE_STATUS_ENUM:
        errors.append(
            f"'license.status' must be one of {sorted(LICENSE_STATUS_ENUM)}, "
            f"got: {license_status!r}"
        )

    # --- provenance.source.acquired_at: ISO 8601 ---
    acquired_at = _get_nested(data, "provenance", "source", "acquired_at")
    if acquired_at is None:
        errors.append("Missing required field: 'provenance.source.acquired_at'")
    elif not _is_iso8601(acquired_at):
        errors.append(
            f"'provenance.source.acquired_at' must be ISO 8601, got: {acquired_at!r}"
        )

    # --- share block ---
    share = data.get("share")
    if not isinstance(share, dict):
        errors.append("Missing or invalid 'share' block (must be an object)")
    else:
        # share.source_pdf_sas_url
        src_url = share.get("source_pdf_sas_url")
        if not src_url or not isinstance(src_url, str) or not src_url.strip():
            errors.append("Missing or empty required field: 'share.source_pdf_sas_url'")
        elif not _SOURCE_PDF_SAS_URL_RE.match(src_url):
            errors.append(
                "share.source_pdf_sas_url must be an HTTPS Azure Blob SAS URL "
                "pointing at book-workspaces/.../input/source.pdf, "
                f"got: {src_url!r}"
            )

        # share.translated_pdf_sas_url
        trs_url = share.get("translated_pdf_sas_url")
        if not trs_url or not isinstance(trs_url, str) or not trs_url.strip():
            errors.append("Missing or empty required field: 'share.translated_pdf_sas_url'")
        elif not _TRANSLATED_PDF_SAS_URL_RE.match(trs_url):
            errors.append(
                "share.translated_pdf_sas_url must be an HTTPS Azure Blob SAS URL "
                "pointing at book-workspaces/.../output/translated.pdf, "
                f"got: {trs_url!r}"
            )

        # share.sas_expiry
        sas_expiry = share.get("sas_expiry")
        if not sas_expiry:
            errors.append("Missing required field: 'share.sas_expiry'")
        elif not _is_iso8601(sas_expiry):
            errors.append(
                f"'share.sas_expiry' must be ISO 8601, got: {sas_expiry!r}"
            )

        # share.generated_at
        gen_at = share.get("generated_at")
        if not gen_at:
            errors.append("Missing required field: 'share.generated_at'")
        elif not _is_iso8601(gen_at):
            errors.append(
                f"'share.generated_at' must be ISO 8601, got: {gen_at!r}"
            )

    if errors:
        raise MetadataValidationError(errors)


# ---------------------------------------------------------------------------
# Promotion eligibility
# ---------------------------------------------------------------------------


def is_eligible_for_promotion(license_status: str) -> bool:
    """Return True iff the book may be promoted to public archive (Shape B).

    Rule: license.status ∈ { "verified-public-domain", "rights-cleared" }
    Source: .squad/decisions.md, Promotion-Eligibility Rule.

    Books with 'rights-unknown' or 'claimed-public-domain' must NOT appear in
    any public catalog, public blob URL, or shareable archive page.
    """
    return license_status in LICENSE_STATUS_PROMOTION_ELIGIBLE
