"""D-3: metadata.json schema validator tests.

Tests the Pydantic-style validator in ``transpose.workspace.metadata_schema``
against the 14-field spec defined in decisions.md (Architecture Addendum §D).

All tests in this file run immediately (no dependency on Trinity or Tank).

Spec reference: .squad/decisions.md — 2026-05-20T23:10:06 Architecture Addendum §D
"""

from __future__ import annotations

import copy

import pytest

from transpose.workspace.metadata_schema import (
    LICENSE_STATUS_ENUM,
    LICENSE_STATUS_PROMOTION_ELIGIBLE,
    MetadataValidationError,
    is_eligible_for_promotion,
    validate_metadata,
)

# ---------------------------------------------------------------------------
# Canonical valid fixture
# Reflects the full §D example from decisions.md with all mandatory-before-share
# fields populated.
# ---------------------------------------------------------------------------

VALID_METADATA: dict = {
    "workspace_id": "ws-a1b2c3d4",
    "book_id": "beacab8b-ea5c-49e5-a60f-1ebc753c7061",
    "slug": "vigyan-bhairav-tantra-vol-1",
    "title": "Vigyan Bhairav Tantra Vol. 1",
    "author": "Osho",
    "source_language": "Hindi",
    "target_language": "English",
    "page_count": 312,
    "status": "review",
    "pipeline_version": "1.3.0",
    "created_at": "2026-05-20T22:52:32-04:00",
    "updated_at": "2026-05-20T23:19:30-04:00",
    "published_at": None,
    "translator_note": "A Tantra classic. 112 meditation techniques.",
    "cover_image_blob_url": None,
    "landing_page_url": (
        "https://transposebooks.z6.web.core.windows.net/"
        "vigyan-bhairav-tantra-vol-1--b7f3a2/"
    ),
    "license": {
        "status": "verified-public-domain",
        "notes": "Pre-1925 text; no modern editorial layer.",
    },
    "provenance": {
        "source": {
            "url": "https://archive.org/details/osho-vbt-vol1-hindi",
            "edition": "Diamond Pocket Books, New Delhi, 2005 edition",
            "acquired_at": "2026-04-01T10:00:00Z",
            "notes": None,
        }
    },
    "share": {
        "source_pdf_sas_url": (
            "https://transposebooks.blob.core.windows.net/book-workspaces/"
            "vigyan-bhairav-tantra-vol-1--b7f3a2/input/source.pdf"
            "?sv=2023-01-03&se=2026-06-19T23%3A10%3A00Z&sr=b&sp=r&sig=FAKESIG002"
        ),
        "translated_pdf_sas_url": (
            "https://transposebooks.blob.core.windows.net/book-workspaces/"
            "vigyan-bhairav-tantra-vol-1--b7f3a2/output/translated.pdf"
            "?sv=2023-01-03&se=2026-06-19T23%3A10%3A00Z&sr=b&sp=r&sig=FAKESIG001"
        ),
        "sas_expiry": "2026-06-19T23:10:00Z",
        "generated_at": "2026-05-20T23:10:06Z",
    },
    "artifact_manifest": [],
}


@pytest.fixture
def valid_metadata() -> dict:
    """Deep-copy of VALID_METADATA to prevent test cross-contamination."""
    return copy.deepcopy(VALID_METADATA)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestValidMetadataPasses:
    def test_valid_metadata_passes_validation(self, valid_metadata: dict) -> None:
        """A fully populated metadata.json matching the spec must pass validation."""
        # Must not raise
        validate_metadata(valid_metadata)

    def test_validate_returns_none_on_success(self, valid_metadata: dict) -> None:
        """validate_metadata() returns None (not a truthy object) on success."""
        result = validate_metadata(valid_metadata)
        assert result is None, (
            "validate_metadata() must return None on success, "
            f"got {result!r}."
        )


# ---------------------------------------------------------------------------
# Missing required fields — parametrized
# ---------------------------------------------------------------------------

# Each entry: (display_name, mutation_fn) where mutation_fn removes the field
# from the metadata dict to simulate a missing value.
_REQUIRED_FIELD_CASES: list[tuple[str, object]] = [
    ("title",                    lambda d: d.pop("title")),
    ("author",                   lambda d: d.pop("author")),
    ("source_language",          lambda d: d.pop("source_language")),
    ("target_language",          lambda d: d.pop("target_language")),
    ("page_count",               lambda d: d.pop("page_count")),
    ("slug",                     lambda d: d.pop("slug")),
    ("landing_page_url",         lambda d: d.pop("landing_page_url")),
    ("share.source_pdf_sas_url", lambda d: d["share"].pop("source_pdf_sas_url")),
    ("share.translated_pdf_sas_url", lambda d: d["share"].pop("translated_pdf_sas_url")),
    ("share.sas_expiry",         lambda d: d["share"].pop("sas_expiry")),
    ("share.generated_at",       lambda d: d["share"].pop("generated_at")),
]


@pytest.mark.parametrize("field_name,mutator", _REQUIRED_FIELD_CASES)
def test_missing_required_field_fails(
    field_name: str, mutator: object, valid_metadata: dict
) -> None:
    """Removing any mandatory-before-share field must raise MetadataValidationError.

    Spec: decisions.md §D — all 11 fields marked '✅ yes' under
    'Mandatory Before Share' must be present and non-empty.
    """
    mutator(valid_metadata)  # type: ignore[operator]
    with pytest.raises(MetadataValidationError) as exc_info:
        validate_metadata(valid_metadata)
    assert exc_info.value.errors, (
        f"MetadataValidationError for missing '{field_name}' must list at least one error."
    )
    combined = " ".join(exc_info.value.errors).lower()
    # The error message should hint at which field failed
    field_hint = field_name.split(".")[-1]
    assert field_hint in combined, (
        f"Error message for missing '{field_name}' should mention the field name. "
        f"Got errors: {exc_info.value.errors}"
    )


# ---------------------------------------------------------------------------
# license.status enum validation
# ---------------------------------------------------------------------------

class TestLicenseStatusValidation:
    def test_invalid_license_status_fails(self, valid_metadata: dict) -> None:
        """license.status set to an out-of-enum value must raise MetadataValidationError.

        Spec: decisions.md — CHECK constraint on license_status enum.
        """
        valid_metadata["license"]["status"] = "made-up-value"
        with pytest.raises(MetadataValidationError) as exc_info:
            validate_metadata(valid_metadata)
        has_license_error = any(
            "license.status" in error or "license" in error.lower()
            for error in exc_info.value.errors
        )
        assert has_license_error, (
            f"Error must mention 'license.status'. Got: {exc_info.value.errors}"
        )

    @pytest.mark.parametrize("status", sorted(LICENSE_STATUS_ENUM))
    def test_all_valid_license_statuses_pass(
        self, status: str, valid_metadata: dict
    ) -> None:
        """Every value in the 4-value enum must pass validation."""
        valid_metadata["license"]["status"] = status
        validate_metadata(valid_metadata)  # must not raise

    def test_missing_license_block_fails(self, valid_metadata: dict) -> None:
        """Absence of the entire license block must raise MetadataValidationError."""
        del valid_metadata["license"]
        with pytest.raises(MetadataValidationError):
            validate_metadata(valid_metadata)

    def test_missing_license_status_key_fails(self, valid_metadata: dict) -> None:
        """license block present but status key absent must raise MetadataValidationError."""
        del valid_metadata["license"]["status"]
        with pytest.raises(MetadataValidationError):
            validate_metadata(valid_metadata)


# ---------------------------------------------------------------------------
# provenance.source.acquired_at — ISO 8601 enforcement
# ---------------------------------------------------------------------------

class TestProvenanceAcquiredAt:
    def test_invalid_acquired_at_fails(self, valid_metadata: dict) -> None:
        """Non-ISO-8601 acquired_at must raise MetadataValidationError.

        Spec: decisions.md — provenance.source.acquired_at is '<ISO 8601 datetime>'.
        """
        valid_metadata["provenance"]["source"]["acquired_at"] = "not-a-date"
        with pytest.raises(MetadataValidationError) as exc_info:
            validate_metadata(valid_metadata)
        assert any("acquired_at" in e for e in exc_info.value.errors), (
            f"Error must mention 'acquired_at'. Got: {exc_info.value.errors}"
        )

    @pytest.mark.parametrize(
        "iso_value",
        [
            "2026-04-01T10:00:00Z",
            "2026-05-20T22:52:32-04:00",
            "2026-05-20T23:19:30.952-04:00",
            "2026-06-19T23:10:00Z",
        ],
    )
    def test_valid_iso8601_acquired_at_passes(
        self, iso_value: str, valid_metadata: dict
    ) -> None:
        """Various ISO 8601 formats seen in the spec must all pass."""
        valid_metadata["provenance"]["source"]["acquired_at"] = iso_value
        validate_metadata(valid_metadata)  # must not raise

    def test_empty_acquired_at_fails(self, valid_metadata: dict) -> None:
        """Empty string for acquired_at must raise MetadataValidationError."""
        valid_metadata["provenance"]["source"]["acquired_at"] = ""
        with pytest.raises(MetadataValidationError):
            validate_metadata(valid_metadata)

    def test_null_acquired_at_fails(self, valid_metadata: dict) -> None:
        """None/null for acquired_at must raise MetadataValidationError.

        Spec: 'acquired_at defaults to the ingest timestamp if not explicitly supplied' —
        it must always be set, never null.
        """
        valid_metadata["provenance"]["source"]["acquired_at"] = None
        with pytest.raises(MetadataValidationError):
            validate_metadata(valid_metadata)


# ---------------------------------------------------------------------------
# Share URL pattern validation
# ---------------------------------------------------------------------------

class TestShareUrlValidation:
    def test_malformed_source_pdf_sas_url_fails(self, valid_metadata: dict) -> None:
        """source_pdf_sas_url not pointing at .../input/source.pdf must fail.

        Spec: decisions.md §B — per-file SAS URL scoped to input/source.pdf.
        """
        valid_metadata["share"]["source_pdf_sas_url"] = "https://example.com/wrong.pdf"
        with pytest.raises(MetadataValidationError) as exc_info:
            validate_metadata(valid_metadata)
        assert any("source_pdf_sas_url" in e for e in exc_info.value.errors), (
            f"Error must mention 'source_pdf_sas_url'. Got: {exc_info.value.errors}"
        )

    def test_malformed_translated_pdf_sas_url_fails(
        self, valid_metadata: dict
    ) -> None:
        """translated_pdf_sas_url not pointing at .../output/translated.pdf must fail.

        Spec: decisions.md §B — per-file SAS URL scoped to output/translated.pdf.
        """
        valid_metadata["share"]["translated_pdf_sas_url"] = (
            "https://example.com/wrong.pdf"
        )
        with pytest.raises(MetadataValidationError) as exc_info:
            validate_metadata(valid_metadata)
        assert any("translated_pdf_sas_url" in e for e in exc_info.value.errors), (
            f"Error must mention 'translated_pdf_sas_url'. Got: {exc_info.value.errors}"
        )

    def test_http_sas_url_fails(self, valid_metadata: dict) -> None:
        """SAS URLs must use HTTPS, not HTTP."""
        valid_metadata["share"]["source_pdf_sas_url"] = (
            "http://transposebooks.blob.core.windows.net/book-workspaces/"
            "test--abc123/input/source.pdf?sv=x&sig=y"
        )
        with pytest.raises(MetadataValidationError):
            validate_metadata(valid_metadata)

    def test_sas_url_without_query_params_fails(self, valid_metadata: dict) -> None:
        """SAS URLs without query parameters (no signature) must fail."""
        valid_metadata["share"]["source_pdf_sas_url"] = (
            "https://transposebooks.blob.core.windows.net/book-workspaces/"
            "test--abc123/input/source.pdf"
        )
        with pytest.raises(MetadataValidationError):
            validate_metadata(valid_metadata)

    def test_sas_url_pointing_at_wrong_container_fails(
        self, valid_metadata: dict
    ) -> None:
        """SAS URL pointing at a container other than book-workspaces must fail.

        Spec: decisions.md §B — all workspace blobs live under book-workspaces/.
        """
        valid_metadata["share"]["source_pdf_sas_url"] = (
            "https://transposebooks.blob.core.windows.net/other-container/"
            "test--abc123/input/source.pdf?sv=x&sig=y"
        )
        with pytest.raises(MetadataValidationError):
            validate_metadata(valid_metadata)


# ---------------------------------------------------------------------------
# Promotion-eligibility integration with schema validation
# ---------------------------------------------------------------------------

class TestPromotionEligibilityIntegration:
    """Cross-check that the validator and promotion rule agree."""

    @pytest.mark.parametrize("status", sorted(LICENSE_STATUS_PROMOTION_ELIGIBLE))
    def test_promotion_eligible_statuses_pass_schema(
        self, status: str, valid_metadata: dict
    ) -> None:
        """Promotion-eligible statuses must also pass schema validation."""
        valid_metadata["license"]["status"] = status
        validate_metadata(valid_metadata)  # must not raise

    @pytest.mark.parametrize(
        "status",
        sorted(LICENSE_STATUS_ENUM - LICENSE_STATUS_PROMOTION_ELIGIBLE),
    )
    def test_promotion_ineligible_statuses_pass_schema_but_fail_promotion(
        self, status: str, valid_metadata: dict
    ) -> None:
        """Ineligible statuses are valid per schema but must fail the promotion gate."""
        valid_metadata["license"]["status"] = status
        validate_metadata(valid_metadata)  # schema: must not raise
        assert not is_eligible_for_promotion(status), (
            f"license.status='{status}' must NOT pass the promotion gate."
        )
