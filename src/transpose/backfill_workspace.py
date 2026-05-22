"""Standalone CLI for backfilling Stage 8 workspace artifacts for old books."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import click

from transpose.config.settings import get_settings
from transpose.pipeline.workspace import (
    BookWorkspace,
    build_metadata,
    generate_landing_html,
    make_blob_prefix,
    make_slug,
    validate_metadata,
)
from transpose.services.blob_client import BlobClient

os.environ.setdefault("PGSSLCRL", "")
os.environ.setdefault("PGSSLCRLDIR", "")

_AZURE_STORAGE_SCOPE = "https://storage.azure.com/.default"


@dataclass(frozen=True)
class BackfillPlan:
    """Derived workspace plan for a single book backfill."""

    book_id: str
    slug: str
    title: str
    author: str
    source_language: str
    target_language: str
    page_count: int
    source_pdf: Path
    translated_pdf: Path
    source_size_bytes: int
    translated_size_bytes: int
    blob_prefix: str
    source_blob_name: str
    translated_blob_name: str
    metadata_blob_name: str
    private_landing_blob_name: str
    public_landing_blob_name: str
    landing_page_url: str | None


@dataclass(frozen=True)
class PreflightResult:
    """Environment validation for Azure-backed workspace backfill."""

    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def _count_pdf_pages(pdf_path: Path) -> int:
    import fitz

    with fitz.open(pdf_path) as pdf:
        return len(pdf)


def build_backfill_plan(
    *,
    book_id: UUID | str,
    slug: str | None,
    title: str,
    author: str,
    source_language: str,
    target_language: str,
    source_pdf: Path,
    translated_pdf: Path,
    page_count: int | None,
    static_website_url: str,
) -> BackfillPlan:
    """Build the deterministic workspace layout for one backfill run."""
    resolved_slug = slug or make_slug(title)
    resolved_book_id = str(book_id)
    resolved_page_count = page_count or _count_pdf_pages(source_pdf)
    blob_prefix = make_blob_prefix(resolved_slug, resolved_book_id)
    landing_page_url = (
        f"{static_website_url.rstrip('/')}/{blob_prefix}/" if static_website_url else None
    )

    return BackfillPlan(
        book_id=resolved_book_id,
        slug=resolved_slug,
        title=title,
        author=author,
        source_language=source_language,
        target_language=target_language,
        page_count=resolved_page_count,
        source_pdf=source_pdf.resolve(),
        translated_pdf=translated_pdf.resolve(),
        source_size_bytes=source_pdf.stat().st_size,
        translated_size_bytes=translated_pdf.stat().st_size,
        blob_prefix=blob_prefix,
        source_blob_name=f"{blob_prefix}/input/source.pdf",
        translated_blob_name=f"{blob_prefix}/output/translated.pdf",
        metadata_blob_name=f"{blob_prefix}/metadata.json",
        private_landing_blob_name=f"{blob_prefix}/landing/index.html",
        public_landing_blob_name=f"{blob_prefix}/index.html",
        landing_page_url=landing_page_url,
    )


async def _check_azure_credentials() -> str | None:
    """Return a friendly error if DefaultAzureCredential cannot get a Storage token."""
    from azure.identity.aio import DefaultAzureCredential

    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    try:
        await credential.get_token(_AZURE_STORAGE_SCOPE)
    except Exception:
        return (
            "Azure credentials are unavailable for Storage. Run scripts/azure-setup.sh "
            "first, then authenticate so DefaultAzureCredential can access the storage account."
        )
    finally:
        await credential.close()
    return None


async def run_preflight() -> PreflightResult:
    """Validate the minimum Azure configuration needed for a real backfill."""
    settings = get_settings()
    issues: list[str] = []

    if not settings.blob_storage_account_url:
        issues.append(
            "TRANSPOSE_BLOB_STORAGE_ACCOUNT_URL is not set. Run scripts/azure-setup.sh first."
        )
    if not settings.blob_static_website_url:
        issues.append(
            "TRANSPOSE_BLOB_STATIC_WEBSITE_URL is not set. Run scripts/azure-setup.sh first."
        )
    if settings.blob_storage_account_url:
        credential_issue = await _check_azure_credentials()
        if credential_issue:
            issues.append(credential_issue)

    return PreflightResult(tuple(issues))


def _build_metadata_payload(
    plan: BackfillPlan,
    *,
    source_url: str | None,
    source_edition: str | None,
    source_acquired_at: str | None,
    source_notes: str | None,
    translator_note: str | None,
    cover_image_blob_url: str | None,
    pipeline_version: str,
) -> dict:
    metadata = build_metadata(
        book_id=plan.book_id,
        slug=plan.slug,
        title=plan.title,
        author=plan.author,
        source_language=plan.source_language,
        target_language=plan.target_language,
        page_count=plan.page_count,
        source_url=source_url,
        source_edition=source_edition,
        source_acquired_at=source_acquired_at,
        source_notes=source_notes,
        translator_note=translator_note,
        cover_image_blob_url=cover_image_blob_url,
        pipeline_version=pipeline_version,
    )
    errors = validate_metadata(metadata)
    if errors:
        raise click.ClickException("metadata.json validation failed: " + "; ".join(errors))
    return metadata


def _format_plan(plan: BackfillPlan, *, dry_run: bool) -> str:
    share_url = (
        plan.landing_page_url
        or "unavailable until TRANSPOSE_BLOB_STATIC_WEBSITE_URL is set"
    )
    mode = "DRY RUN" if dry_run else "RUN"
    return "\n".join([
        f"[{mode}] Workspace backfill for {plan.title}",
        f"book_id: {plan.book_id}",
        f"slug: {plan.slug}",
        f"workspace prefix: {plan.blob_prefix}",
        f"source pdf: {plan.source_pdf} ({plan.source_size_bytes} bytes)",
        f"translated pdf: {plan.translated_pdf} ({plan.translated_size_bytes} bytes)",
        f"page_count: {plan.page_count}",
        f"would upload: book-workspaces/{plan.source_blob_name}",
        f"would upload: book-workspaces/{plan.translated_blob_name}",
        f"would write: book-workspaces/{plan.metadata_blob_name}",
        f"would publish: book-workspaces/{plan.private_landing_blob_name}",
        f"would publish: $web/{plan.public_landing_blob_name}",
        f"share url: {share_url}",
    ])


async def backfill_workspace(
    *,
    book_id: UUID,
    slug: str | None,
    source_pdf: Path,
    translated_pdf: Path,
    title: str,
    author: str,
    source_lang: str,
    target_lang: str,
    page_count: int | None,
    source_url: str | None,
    source_edition: str | None,
    source_acquired_at: str | None,
    source_notes: str | None,
    translator_note: str | None,
    cover_image_blob_url: str | None,
    pipeline_version: str,
    dry_run: bool,
    allow_local_fallback: bool,
) -> int:
    """Backfill Stage 8 artifacts for an already-translated book."""
    settings = get_settings()
    plan = build_backfill_plan(
        book_id=book_id,
        slug=slug,
        title=title,
        author=author,
        source_language=source_lang,
        target_language=target_lang,
        source_pdf=source_pdf,
        translated_pdf=translated_pdf,
        page_count=page_count,
        static_website_url=settings.blob_static_website_url,
    )
    click.echo(_format_plan(plan, dry_run=dry_run))

    metadata = _build_metadata_payload(
        plan,
        source_url=source_url,
        source_edition=source_edition,
        source_acquired_at=source_acquired_at,
        source_notes=source_notes,
        translator_note=translator_note,
        cover_image_blob_url=cover_image_blob_url,
        pipeline_version=pipeline_version,
    )
    metadata["landing_page_url"] = plan.landing_page_url
    preview_html = generate_landing_html(metadata)

    preflight = await run_preflight()
    if dry_run:
        click.echo("would set metadata license.status=rights-unknown")
        click.echo(
            "would generate 30-day read-only SAS URLs for source.pdf and translated.pdf"
        )
        click.echo(
            f"would render landing page HTML ({len(preview_html)} chars) "
            "and upload it idempotently"
        )
        if not preflight.ok:
            raise click.ClickException("Preflight failed:\n- " + "\n- ".join(preflight.issues))
        click.echo("dry-run complete: Azure configuration looks ready; no uploads were performed")
        return 0

    if not preflight.ok:
        if not allow_local_fallback:
            raise click.ClickException("Preflight failed:\n- " + "\n- ".join(preflight.issues))
        click.echo(
            "⚠️  --allow-local-fallback is enabled; continuing despite Azure preflight issues"
        )
        for issue in preflight.issues:
            click.echo(f"  - {issue}")

    blob_client = BlobClient(
        settings.blob_storage_account_url,
        allow_local_fallback=allow_local_fallback,
        on_rbac_retry=click.echo,
    )
    ws = BookWorkspace(
        book_id=plan.book_id,
        slug=plan.slug,
        blob_client=blob_client,
        static_website_url=settings.blob_static_website_url,
    )
    try:
        await ws.upload_source(plan.source_pdf)
        await ws.upload_translated(plan.translated_pdf)
        await ws.write_metadata(metadata)

        now_utc = datetime.now(UTC)
        source_sas = await ws.generate_sas_url(ws.source_blob_name, expiry_days=30)
        translated_sas = await ws.generate_sas_url(ws.translated_blob_name, expiry_days=30)
        sas_expiry = (now_utc + timedelta(days=30)).isoformat()

        metadata["landing_page_url"] = ws.landing_page_url
        metadata["share"]["source_pdf_sas_url"] = source_sas
        metadata["share"]["translated_pdf_sas_url"] = translated_sas
        metadata["share"]["sas_expiry"] = sas_expiry
        metadata["share"]["generated_at"] = now_utc.isoformat()

        html_str = generate_landing_html(metadata)
        public_url = await ws.publish_landing_page(html_str)
        await ws.update_metadata({
            "landing_page_url": public_url,
            "share": {
                "source_pdf_sas_url": source_sas,
                "translated_pdf_sas_url": translated_sas,
                "sas_expiry": sas_expiry,
                "generated_at": now_utc.isoformat(),
            },
        })
    finally:
        await blob_client.close()

    click.echo(f"share url: {public_url}")
    return 0


@click.command()
@click.option("--book-id", required=True, type=click.UUID, help="Existing book UUID.")
@click.option("--slug", default=None, help="Landing-page slug. Defaults to make_slug(title).")
@click.option(
    "--source-pdf",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the original source PDF.",
)
@click.option(
    "--translated-pdf",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the already-translated PDF.",
)
@click.option("--title", required=True, help="Book title for metadata.json.")
@click.option("--author", required=True, help="Book author for metadata.json.")
@click.option("--source-lang", required=True, help="Source language label, e.g. Hindi.")
@click.option(
    "--target-lang",
    default="English",
    show_default=True,
    help="Target language label.",
)
@click.option(
    "--page-count",
    type=int,
    default=None,
    help="Override page_count; defaults to source PDF pages.",
)
@click.option("--source-url", default=None, help="Optional provenance.source.url.")
@click.option("--source-edition", default=None, help="Optional provenance.source.edition.")
@click.option(
    "--source-acquired-at",
    default=None,
    help="Optional provenance.source.acquired_at ISO timestamp.",
)
@click.option("--source-notes", default=None, help="Optional provenance.source.notes.")
@click.option(
    "--translator-note",
    default=None,
    help="Optional landing-page description override.",
)
@click.option("--cover-image-blob-url", default=None, help="Optional OG image URL.")
@click.option(
    "--pipeline-version",
    default="backfill-workspace/1.0",
    show_default=True,
    help="metadata.json pipeline_version.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print planned actions without uploading to Azure.",
)
@click.option(
    "--allow-local-fallback",
    is_flag=True,
    default=False,
    help="Dev/test only: fall back to output/blob if Azure Blob stays unavailable.",
)
def main(
    book_id: UUID,
    slug: str | None,
    source_pdf: Path,
    translated_pdf: Path,
    title: str,
    author: str,
    source_lang: str,
    target_lang: str,
    page_count: int | None,
    source_url: str | None,
    source_edition: str | None,
    source_acquired_at: str | None,
    source_notes: str | None,
    translator_note: str | None,
    cover_image_blob_url: str | None,
    pipeline_version: str,
    dry_run: bool,
    allow_local_fallback: bool,
) -> None:
    """Backfill Stage 8 workspace artifacts for a pre-Stage-8 translated book."""
    try:
        exit_code = asyncio.run(
            backfill_workspace(
                book_id=book_id,
                slug=slug,
                source_pdf=source_pdf,
                translated_pdf=translated_pdf,
                title=title,
                author=author,
                source_lang=source_lang,
                target_lang=target_lang,
                page_count=page_count,
                source_url=source_url,
                source_edition=source_edition,
                source_acquired_at=source_acquired_at,
                source_notes=source_notes,
                translator_note=translator_note,
                cover_image_blob_url=cover_image_blob_url,
                pipeline_version=pipeline_version,
                dry_run=dry_run,
                allow_local_fallback=allow_local_fallback,
            )
        )
    except click.ClickException:
        raise
    except Exception as exc:  # pragma: no cover - defensive CLI guard
        raise click.ClickException(f"{type(exc).__name__}: {exc}") from exc

    if exit_code:
        raise SystemExit(exit_code)
