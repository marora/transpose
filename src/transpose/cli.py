"""CLI entry point for the Transpose pipeline."""

from __future__ import annotations

# TLS workaround: prevent CRL lookup hang with Azure PostgreSQL on WSL2.
# Must be set before any database driver is imported.
import os

os.environ.setdefault("PGSSLCRL", "")
os.environ.setdefault("PGSSLCRLDIR", "")

import asyncio
import logging

import click


@click.group()
def main() -> None:
    """Transpose — translate Hindi/Punjabi books to English."""
    from transpose.config.settings import get_appinsights_connection_string
    from transpose.observability.tracing import configure_tracing

    configure_tracing(get_appinsights_connection_string())


@main.command()
@click.option("--source", required=True, help="Path to source PDF file")
@click.option("--title", required=True, help="Book title")
@click.option("--author", default=None, help="Book author")
@click.option("--language", type=click.Choice(["hindi", "punjabi"]), default="hindi")
@click.option("--format", "formats", multiple=True, default=["epub", "pdf"])
@click.option("--resume-from", default=None, help="Stage to resume from")
@click.option("--concurrency", type=int, default=None, help="Translation concurrency (default: from settings)")
@click.option("--force", is_flag=True, default=False, help="Force re-translation of all chunks (ignore cache)")
def run(
    source: str,
    title: str,
    author: str | None,
    language: str,
    formats: tuple[str, ...],
    resume_from: str | None,
    concurrency: int | None,
    force: bool,
) -> None:
    """Run the translation pipeline on a book."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    click.echo(f"Transpose: translating '{title}' from {language}")

    # Run the pipeline
    asyncio.run(_run_pipeline(source, title, author, language, list(formats), resume_from, concurrency, force))


async def _run_pipeline(
    source: str,
    title: str,
    author: str | None,
    language: str,
    formats: list[str],
    resume_from: str | None,
    concurrency: int | None = None,
    force: bool = False,
) -> None:
    """Async pipeline runner."""
    from transpose.models.enums import SourceLanguage
    from transpose.pipeline.runner import PipelineInput, run_pipeline
    from transpose.services import ServiceContext

    # Create service context
    ctx = ServiceContext()
    await ctx.connect()

    try:
        # Build pipeline input
        source_language = SourceLanguage.HINDI if language == "hindi" else SourceLanguage.PUNJABI

        # Detect URL sources and route to blob_uri for download
        is_url = source.startswith("http://") or source.startswith("https://")
        pipeline_input = PipelineInput(
            source_path=source if not is_url else "",
            title=title,
            author=author,
            source_language=source_language,
            output_formats=formats,
            resume_from=resume_from,
            blob_uri=source if is_url else None,
            concurrency=concurrency,
            force_retranslate=force,
        )

        # Run pipeline
        output = await run_pipeline(pipeline_input, ctx)

        # Display results
        click.echo("\n✅ Pipeline complete!")
        click.echo(f"Book ID: {output.book_id}")
        click.echo(f"Status: {output.status}")
        click.echo(f"Stages completed: {', '.join(output.stages_completed)}")
        click.echo(f"Glossary terms: {output.glossary_term_count}")
        click.echo(f"Total tokens used: {output.total_tokens_used}")

        if output.artifacts:
            click.echo("\nArtifacts:")
            for artifact in output.artifacts:
                click.echo(f"  - {artifact['format']}: {artifact['blob_uri']}")

        if output.errors:
            click.echo("\nErrors:")
            for error in output.errors:
                click.echo(f"  - {error['stage']}: {error['error']}")

    except Exception as e:
        click.echo(f"\n❌ Pipeline failed: {e}", err=True)
        raise
    finally:
        await ctx.close()


@main.command()
@click.option("--book-id", required=True, help="Book UUID")
def status(book_id: str) -> None:
    """Check pipeline status for a book."""
    click.echo(f"Checking status for book {book_id}...")

    # Run async status check
    asyncio.run(_check_status(book_id))


async def _check_status(book_id: str) -> None:
    """Async status checker."""
    from transpose.services import ServiceContext

    ctx = ServiceContext()
    await ctx.connect()

    try:
        # Get book from database
        from uuid import UUID

        book = await ctx.db.get_book(UUID(book_id))

        if not book:
            click.echo(f"Book not found: {book_id}")
            return

        # Get pipeline status from state
        pipeline_status = await ctx.state.get_pipeline_status(book_id)

        # Display status
        click.echo(f"\nBook: {book.title}")
        if book.author:
            click.echo(f"Author: {book.author}")
        click.echo(f"Status: {book.status}")
        click.echo(f"Pages: {book.page_count}")

        if pipeline_status:
            click.echo(f"Current stage: {pipeline_status}")

        # Get manuscript if available
        if book.status in ["assembled", "exported"]:
            manuscript = await ctx.db.get_manuscript_for_book(UUID(book_id))
            if manuscript:
                click.echo(f"Chapters: {len(manuscript.chapters)}")

            glossary = await ctx.db.get_glossary_for_book(UUID(book_id))
            if glossary:
                click.echo(f"Glossary terms: {len(glossary.entries)}")

    finally:
        await ctx.close()


if __name__ == "__main__":
    main()

