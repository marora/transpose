"""D-1: License constraint tests.

Tests the four-layer `rights-unknown` enforcement (decisions.md §E):

  Layer 1 – DB CHECK constraint (Tank T-2)
    → see tests/integration/test_license_db_constraints.py
  Layer 2 – Application ingest guard (Trinity TR-1)
  Layer 3 – metadata.json writer guard (Trinity TR-2)
  Layer 4 – Export/publish stage gate (Trinity TR-1 + TR-3)

Tests that exercise code not yet written by Tank or Trinity are marked
``pytest.mark.contract`` and automatically skipped until those
implementations are merged.  The promotion-eligibility rule tests (pure
logic in metadata_schema.py) are unconditionally runnable.

Spec references: .squad/decisions.md
  - 2026-05-20T22:52:32-04:00 BookWorkspace schema extension
  - Architecture Addendum §E (four-layer enforcement)
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from transpose.workspace.metadata_schema import (
    LICENSE_STATUS_DEFAULT,
    LICENSE_STATUS_ENUM,
    LICENSE_STATUS_PROMOTION_ELIGIBLE,
    is_eligible_for_promotion,
)

# ---------------------------------------------------------------------------
# Contract import guards — skipped until Trinity lands TR-1 / TR-2
#
# IMPORTANT: use importlib.util.find_spec() instead of bare imports so that
# collection-time module loading does NOT set the package attribute on
# ``transpose.pipeline``.  Module-level ``from transpose.pipeline.ingest
# import ...`` would cache the real module as ``sys.modules["transpose.pipeline"].ingest``,
# which breaks the ``monkeypatch.setitem(sys.modules, ...)`` strategy in
# test_runner.py's ``_patch_stages`` fixture (relative imports resolve via the
# package attribute, not sys.modules, once the attribute is set).
# ---------------------------------------------------------------------------

HAS_INGEST_MODULE = importlib.util.find_spec("transpose.pipeline.ingest") is not None
HAS_WORKSPACE_MODULE = importlib.util.find_spec("transpose.workspace.workspace") is not None
HAS_EXPORT_MODULE = importlib.util.find_spec("transpose.pipeline.export") is not None

# The export module exists today, but Trinity's license gate (TR-1/TR-3) is not yet
# implemented.  We check for a sentinel that Trinity will add when the gate lands.
# Import lazily here to avoid setting the package attribute at collection time.
def _export_has_license_gate() -> bool:
    if not HAS_EXPORT_MODULE:
        return False
    try:
        import importlib
        mod = importlib.import_module("transpose.pipeline.export")
        return hasattr(mod.run, "_license_gate_enforced")
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ingest_context() -> MagicMock:
    """Minimal ServiceContext mock for ingest stage tests."""
    ctx = MagicMock()
    ctx.db = AsyncMock()
    ctx.blob = AsyncMock()
    ctx.settings = MagicMock()
    ctx.settings.blob_container_source = "source-pdfs"

    # DB returns no existing book (fresh ingest path)
    ctx.db.get_book_by_hash = AsyncMock(return_value=None)

    # Simulate DB creating book and returning it with license_status = 'rights-unknown'
    created_book = MagicMock()
    created_book.license_status = "rights-unknown"
    ctx.db.create_book = AsyncMock(return_value=None)
    ctx.db.get_book = AsyncMock(return_value=created_book)

    ctx.blob.upload_pdf = AsyncMock(
        return_value="https://transposedevst.blob.core.windows.net/source-pdfs/abc123.pdf"
    )
    return ctx


@pytest.fixture
def tmp_pdf(tmp_path: Path) -> Path:
    """Minimal valid PDF bytes written to a temp file."""
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n%%EOF\n"
    )
    p = tmp_path / "source.pdf"
    p.write_bytes(pdf_bytes)
    return p


# ---------------------------------------------------------------------------
# D-1 — Promotion eligibility (pure logic — always runnable)
# ---------------------------------------------------------------------------

class TestPromotionEligibilityRule:
    """The promotion gate is a pure predicate on license.status.

    Rule: license.status ∈ {verified-public-domain, rights-cleared} → eligible
    Source: decisions.md — Promotion-Eligibility Rule.
    """

    def test_verified_public_domain_is_eligible(self) -> None:
        """'verified-public-domain' must clear the promotion gate."""
        assert is_eligible_for_promotion("verified-public-domain"), (
            "Books with license.status='verified-public-domain' must be "
            "eligible for Shape B public archive promotion."
        )

    def test_rights_cleared_is_eligible(self) -> None:
        """'rights-cleared' must clear the promotion gate."""
        assert is_eligible_for_promotion("rights-cleared"), (
            "Books with license.status='rights-cleared' must be "
            "eligible for Shape B public archive promotion."
        )

    def test_rights_unknown_is_ineligible(self) -> None:
        """'rights-unknown' must NOT clear the promotion gate."""
        assert not is_eligible_for_promotion("rights-unknown"), (
            "Books with license.status='rights-unknown' must remain "
            "workspace-private; public promotion must be refused."
        )

    def test_claimed_public_domain_is_ineligible(self) -> None:
        """'claimed-public-domain' must NOT clear the promotion gate.

        Manish's explicit rule (decisions.md Niobe Q1 answer):
        'Keep them fully private until I have upgraded them to verified-public-domain.'
        """
        assert not is_eligible_for_promotion("claimed-public-domain"), (
            "Books with license.status='claimed-public-domain' must remain "
            "workspace-private per Manish's explicit rule."
        )

    def test_exactly_two_statuses_are_eligible(self) -> None:
        """Confirm the full eligible set contains exactly the two expected values."""
        assert frozenset(
            {"verified-public-domain", "rights-cleared"}
        ) == LICENSE_STATUS_PROMOTION_ELIGIBLE, (
            "Only 'verified-public-domain' and 'rights-cleared' should qualify "
            "for public archive promotion."
        )

    def test_default_license_status_is_ineligible(self) -> None:
        """The default workspace status ('rights-unknown') must be ineligible."""
        assert not is_eligible_for_promotion(LICENSE_STATUS_DEFAULT), (
            f"Default license status '{LICENSE_STATUS_DEFAULT}' must never "
            "pass the promotion gate — workspaces start private."
        )


# ---------------------------------------------------------------------------
# D-1 — License status enum coverage (always runnable)
# ---------------------------------------------------------------------------

class TestLicenseStatusEnum:
    """The enum must contain exactly the four values from the spec."""

    def test_enum_contains_all_four_values(self) -> None:
        """license.status enum must match the spec exactly (no more, no less)."""
        expected = frozenset(
            {
                "rights-unknown",
                "claimed-public-domain",
                "verified-public-domain",
                "rights-cleared",
            }
        )
        assert expected == LICENSE_STATUS_ENUM, (
            f"LICENSE_STATUS_ENUM {LICENSE_STATUS_ENUM!r} does not match "
            f"the spec-mandated values {expected!r}."
        )

    def test_rights_unknown_is_the_default(self) -> None:
        """The default value written at workspace creation must be 'rights-unknown'."""
        assert LICENSE_STATUS_DEFAULT == "rights-unknown", (
            f"Default license status must be 'rights-unknown', got '{LICENSE_STATUS_DEFAULT}'."
        )


# ---------------------------------------------------------------------------
# D-1 — Ingest sets rights-unknown (contract: Trinity TR-1)
# ---------------------------------------------------------------------------

@pytest.mark.contract
@pytest.mark.skipif(
    not HAS_INGEST_MODULE,
    reason=(
        "Contract test — requires Trinity TR-1 "
        "(transpose.pipeline.ingest with license_status guard)"
    ),
)
class TestIngestSetsRightsUnknown:
    """Layer 2 enforcement: ingest function must always produce rights-unknown."""

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Trinity TR-1 not yet implemented — Book model has no license_status field",
        strict=False,
    )
    async def test_ingest_sets_rights_unknown(
        self, ingest_context: MagicMock, tmp_pdf: Path
    ) -> None:
        """ingest_book() must produce a book with license_status='rights-unknown'.

        Spec: decisions.md §E Layer 2 — the ingest function must never accept
        license_status as a parameter and must assert the DB default was applied.
        """
        from transpose.pipeline.ingest import IngestInput  # type: ignore[import]
        from transpose.pipeline.ingest import run as ingest_run

        inp = IngestInput(
            source_path=str(tmp_pdf),
            title="Vigyan Bhairav Tantra Vol. 1",
            author="Osho",
        )

        with patch("fitz.open") as mock_fitz_open:
            mock_doc = MagicMock()
            mock_doc.__len__ = MagicMock(return_value=10)
            mock_doc.close = MagicMock()
            mock_fitz_open.return_value = mock_doc

            output = await ingest_run(inp, ingest_context)

        book = await ingest_context.db.get_book(output.book_id)
        assert hasattr(book, "license_status"), (
            "Book model must have a 'license_status' field after Trinity TR-1 lands."
        )
        assert book.license_status == "rights-unknown", (
            f"After ingest, book.license_status must be 'rights-unknown', "
            f"got {book.license_status!r}. "
            "Trinity TR-1: the ingest function must never set license_status."
        )

    def test_ingest_rejects_license_param(self) -> None:
        """ingest_book() must NOT accept license_status as a parameter.

        Spec: decisions.md §E Layer 2 — 'license_status is NOT a parameter. Period.'
        Passing it must raise TypeError (unexpected keyword argument).
        """
        from transpose.pipeline.ingest import IngestInput

        with pytest.raises(TypeError, match="license_status"):
            # license_status is NOT a valid field on IngestInput
            IngestInput(
                source_path="/path/book.pdf",
                title="Test Book",
                license_status="claimed-public-domain",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# D-1 — metadata.json always written with rights-unknown (contract: Trinity TR-2)
# ---------------------------------------------------------------------------

@pytest.mark.contract
@pytest.mark.skipif(
    not HAS_WORKSPACE_MODULE,
    reason="Contract test — requires Trinity TR-2 (transpose.workspace.workspace.BookWorkspace)",
)
class TestMetadataJsonDefaultRightsUnknown:
    """Layer 3 enforcement: the metadata.json writer must always set rights-unknown."""

    def test_metadata_json_default_is_rights_unknown(self, tmp_path: Path) -> None:
        """BookWorkspace.create() must write metadata.json with license.status='rights-unknown'.

        Spec: decisions.md §E Layer 3 — 'Always set license.status="rights-unknown"
        when creating a new workspace. Never accept a license_status override.'
        """
        from transpose.workspace.workspace import BookWorkspace  # type: ignore[import]

        BookWorkspace.create(
            workspace_dir=tmp_path,
            title="Test Book",
            author="Test Author",
            source_language="Hindi",
            target_language="English",
            slug="test-book",
        )

        metadata_path = tmp_path / "metadata.json"
        assert metadata_path.exists(), (
            "BookWorkspace.create() must write a metadata.json file."
        )

        metadata = json.loads(metadata_path.read_text())
        assert metadata.get("license", {}).get("status") == "rights-unknown", (
            f"metadata.json must be created with license.status='rights-unknown', "
            f"got: {metadata.get('license', {}).get('status')!r}."
        )

    def test_workspace_creation_raises_if_license_status_passed(
        self, tmp_path: Path
    ) -> None:
        """BookWorkspace.create() must raise if a caller attempts to override license_status.

        Spec: decisions.md §E Layer 3 — 'Never accept a license_status override
        from pipeline config or environment.'
        """
        from transpose.workspace.workspace import BookWorkspace  # type: ignore[import]

        with pytest.raises((TypeError, ValueError, AssertionError)):
            BookWorkspace.create(
                workspace_dir=tmp_path,
                title="Test Book",
                author="Test Author",
                source_language="Hindi",
                target_language="English",
                slug="test-book",
                license_status="claimed-public-domain",  # type: ignore[call-arg]
            )


# ---------------------------------------------------------------------------
# D-1 — Export hook refuses to flip license_status (contract: Trinity TR-3)
# ---------------------------------------------------------------------------

@pytest.mark.contract
@pytest.mark.skipif(
    not HAS_EXPORT_MODULE,
    reason="Contract test — requires Trinity TR-3 (export/publish stage with license gate)",
)
class TestExportHookRefusesLicenseStatusFlip:
    """Layer 4: export/publish stage must check license.status and refuse ineligible books.

    Spec: decisions.md §E Layer 4 — 'The export/publish stage must check this
    and refuse to promote otherwise' (fail hard, not warn).
    Also: decisions.md Implementation Handoff (Trinity) —
    'check license.status before emitting any public-facing artifact.
    Fail hard (not warn) if status is not in {verified-public-domain, rights-cleared}.'
    """

    @pytest.mark.xfail(
        reason="Trinity TR-3 not yet implemented — export stage has no license gate sentinel",
        strict=False,
    )
    def test_export_has_license_gate_sentinel(self) -> None:
        """export.run must expose a '_license_gate_enforced' sentinel once Trinity TR-3 lands.

        This is a lightweight sync check — it avoids calling export_run (which has
        deeply-nested async DB calls) before the gate is implemented.  The sentinel
        pattern is defined in decisions.md §E Layer 4.
        """
        from transpose.pipeline.export import run as _export_run  # type: ignore[import]

        assert hasattr(_export_run, "_license_gate_enforced"), (
            "Trinity TR-3: export.run must expose '_license_gate_enforced = True' "
            "so Dozer's contract tests can detect the gate without invoking the full pipeline."
        )

