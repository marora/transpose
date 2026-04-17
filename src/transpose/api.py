"""Lightweight HTTP API for triggering the Transpose pipeline.

Designed for Azure Container Apps deployment. Runs on port 8000.

Endpoints:
    GET  /health            → health check
    POST /translate         → trigger pipeline (returns book_id)
    GET  /status/{book_id}  → poll pipeline status
"""

from __future__ import annotations

# TLS workaround: prevent CRL lookup hang with Azure PostgreSQL.
import os

os.environ.setdefault("PGSSLCRL", "")
os.environ.setdefault("PGSSLCRLDIR", "")

import asyncio
import contextlib
import json
import logging
from uuid import UUID, uuid4

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# In-memory job tracker (book_id → status dict).
# For single-replica Container Apps this is sufficient; multi-replica would use Redis/DB.
_jobs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def health(_request: web.Request) -> web.Response:
    """Health probe for Container Apps."""
    return web.json_response({"status": "healthy"})


async def translate(request: web.Request) -> web.Response:
    """Accept a translation request and run the pipeline in background."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception):
        return web.json_response({"error": "invalid JSON body"}, status=400)

    # Validate required fields
    blob_uri = body.get("blob_uri")
    title = body.get("title")
    if not blob_uri or not title:
        return web.json_response({"error": "blob_uri and title are required"}, status=400)

    language = body.get("language", "hindi")
    if language not in ("hindi", "punjabi"):
        return web.json_response({"error": "language must be 'hindi' or 'punjabi'"}, status=400)

    author = body.get("author")
    formats = body.get("formats", ["epub", "pdf"])

    book_id = str(uuid4())
    _jobs[book_id] = {
        "book_id": book_id,
        "status": "accepted",
        "stage": None,
        "error": None,
    }

    # Fire-and-forget pipeline task
    asyncio.create_task(
        _run_pipeline_job(book_id, blob_uri, title, author, language, formats)
    )

    return web.json_response({"book_id": book_id, "status": "accepted"})


async def get_status(request: web.Request) -> web.Response:
    """Return pipeline status for a book."""
    book_id = request.match_info["book_id"]

    # Check in-memory tracker first
    job = _jobs.get(book_id)
    if job:
        return web.json_response(job)

    # Fall back to database lookup
    try:
        UUID(book_id)
    except ValueError:
        return web.json_response({"error": "invalid book_id format"}, status=400)

    try:
        from transpose.services import ServiceContext

        ctx = ServiceContext()
        await ctx.connect()
        try:
            book = await ctx.db.get_book(UUID(book_id))
            if not book:
                return web.json_response({"error": "book not found"}, status=404)
            return web.json_response({
                "book_id": book_id,
                "status": str(book.status),
                "title": book.title,
                "page_count": book.page_count,
            })
        finally:
            await ctx.close()
    except Exception as exc:
        logger.exception("Error fetching status from DB")
        return web.json_response({"error": str(exc)}, status=500)


# ---------------------------------------------------------------------------
# Background pipeline runner
# ---------------------------------------------------------------------------


async def _run_pipeline_job(
    book_id: str,
    blob_uri: str,
    title: str,
    author: str | None,
    language: str,
    formats: list[str],
) -> None:
    """Run the full pipeline in background and update the job tracker."""
    from transpose.models.enums import SourceLanguage
    from transpose.pipeline.runner import PipelineInput, run_pipeline
    from transpose.services import ServiceContext

    _jobs[book_id]["status"] = "running"

    ctx = ServiceContext()
    try:
        await ctx.connect()

        source_language = SourceLanguage.HINDI if language == "hindi" else SourceLanguage.PUNJABI

        pipeline_input = PipelineInput(
            source_path="",  # unused when blob_uri is set
            title=title,
            author=author,
            source_language=source_language,
            output_formats=formats,
            blob_uri=blob_uri,
        )

        output = await run_pipeline(pipeline_input, ctx)

        _jobs[book_id].update({
            "status": "completed",
            "stage": "export",
            "book_id": str(output.book_id),
            "stages_completed": output.stages_completed,
            "glossary_terms": output.glossary_term_count,
            "artifacts": output.artifacts,
        })

    except Exception as exc:
        logger.exception(f"Pipeline failed for {book_id}")
        _jobs[book_id].update({
            "status": "failed",
            "error": str(exc),
        })
    finally:
        with contextlib.suppress(Exception):
            await ctx.close()


# ---------------------------------------------------------------------------
# App factory & entrypoint
# ---------------------------------------------------------------------------


def create_app() -> web.Application:
    """Build the aiohttp application."""
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/translate", translate)
    app.router.add_get("/status/{book_id}", get_status)
    return app


def main() -> None:
    """Run the HTTP server on port 8000."""
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting Transpose API on port {port}")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
