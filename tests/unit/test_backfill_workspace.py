"""Tests for the Stage 8 backfill workspace CLI."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import fitz
from click.testing import CliRunner

from transpose.backfill_workspace import PreflightResult, build_backfill_plan, main


def _make_pdf(path, pages: int = 1) -> None:
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(path)
    doc.close()


class TestBuildBackfillPlan:
    """Plan derivation is deterministic and uses Stage 8 blob paths."""

    def test_defaults_slug_and_page_count(self, tmp_path) -> None:
        source_pdf = tmp_path / "source.pdf"
        translated_pdf = tmp_path / "translated.pdf"
        _make_pdf(source_pdf, pages=3)
        _make_pdf(translated_pdf, pages=5)

        plan = build_backfill_plan(
            book_id=UUID("beacab8b-ea5c-49e5-a60f-1ebc753c7061"),
            slug=None,
            title="Vigyan Bhairav Tantra Volume 1",
            author="Osho",
            source_language="Hindi",
            target_language="English",
            source_pdf=source_pdf,
            translated_pdf=translated_pdf,
            page_count=None,
            static_website_url="https://transposebooks.z6.web.core.windows.net",
        )

        assert plan.slug == "vigyan-bhairav-tantra-volume-1"
        assert plan.page_count == 3
        assert plan.blob_prefix == "vigyan-bhairav-tantra-volume-1--3c7061"
        assert plan.source_blob_name.endswith("/input/source.pdf")
        assert plan.translated_blob_name.endswith("/output/translated.pdf")
        assert plan.landing_page_url == (
            "https://transposebooks.z6.web.core.windows.net/"
            "vigyan-bhairav-tantra-volume-1--3c7061/"
        )


class TestBackfillWorkspaceCli:
    """Dry-run mode should be informative and fail cleanly on missing setup."""

    @patch(
        "transpose.backfill_workspace.run_preflight",
        new=AsyncMock(
            return_value=PreflightResult((
                "TRANSPOSE_BLOB_STATIC_WEBSITE_URL is not set. Run scripts/azure-setup.sh first.",
            ))
        ),
    )
    @patch(
        "transpose.backfill_workspace.get_settings",
        return_value=SimpleNamespace(
            blob_static_website_url="",
            blob_storage_account_url="",
        ),
    )
    def test_dry_run_reports_plan_and_setup_error(self, _mock_settings) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_pdf = "source.pdf"
            translated_pdf = "translated.pdf"
            _make_pdf(source_pdf, pages=2)
            _make_pdf(translated_pdf, pages=4)

            result = runner.invoke(
                main,
                [
                    "--book-id", "beacab8b-ea5c-49e5-a60f-1ebc753c7061",
                    "--source-pdf", source_pdf,
                    "--translated-pdf", translated_pdf,
                    "--title", "Vigyan Bhairav Tantra Volume 1",
                    "--author", "Osho",
                    "--source-lang", "Hindi",
                    "--dry-run",
                ],
            )

        assert result.exit_code != 0
        assert "workspace prefix: vigyan-bhairav-tantra-volume-1--3c7061" in result.output
        assert "would set metadata license.status=rights-unknown" in result.output
        assert "scripts/azure-setup.sh" in result.output

    @patch(
        "transpose.backfill_workspace.run_preflight",
        new=AsyncMock(return_value=PreflightResult(())),
    )
    @patch(
        "transpose.backfill_workspace.get_settings",
        return_value=SimpleNamespace(
            blob_static_website_url="https://transposebooks.z6.web.core.windows.net",
            blob_storage_account_url="https://transposedevst.blob.core.windows.net",
        ),
    )
    def test_dry_run_succeeds_without_uploading(self, _mock_settings) -> None:
        runner = CliRunner()
        with runner.isolated_filesystem():
            source_pdf = "source.pdf"
            translated_pdf = "translated.pdf"
            _make_pdf(source_pdf, pages=2)
            _make_pdf(translated_pdf, pages=4)

            result = runner.invoke(
                main,
                [
                    "--book-id", "beacab8b-ea5c-49e5-a60f-1ebc753c7061",
                    "--source-pdf", source_pdf,
                    "--translated-pdf", translated_pdf,
                    "--title", "Vigyan Bhairav Tantra Volume 1",
                    "--author", "Osho",
                    "--source-lang", "Hindi",
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0
        assert (
            "dry-run complete: Azure configuration looks ready; no uploads were performed"
            in result.output
        )
