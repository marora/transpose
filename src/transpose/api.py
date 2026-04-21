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
import hmac
import json
import logging
from uuid import UUID, uuid4

from aiohttp import web

from transpose.config.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class JobTracker:
    """PostgreSQL-backed job status tracker."""

    def __init__(self):
        self._ctx = None

    async def connect(self):
        """Initialize database connection."""
        from transpose.services import ServiceContext

        self._ctx = ServiceContext()
        await self._ctx.connect()
        # Ensure jobs table exists
        await self._ctx.db.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_jobs (
                book_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'accepted',
                stage TEXT,
                error TEXT,
                result JSONB,
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            )
        """)

    async def create_job(self, book_id: str) -> dict:
        job = {"book_id": book_id, "status": "accepted", "stage": None, "error": None}
        await self._ctx.db.execute(
            """INSERT INTO pipeline_jobs (book_id, status) VALUES ($1, 'accepted')
               ON CONFLICT (book_id) DO UPDATE SET status = 'accepted', updated_at = now()""",
            book_id,
        )
        return job

    async def update_job(self, book_id: str, **kwargs) -> None:
        sets = []
        args = []
        i = 1
        for key, val in kwargs.items():
            if key in ('status', 'stage', 'error'):
                sets.append(f"{key} = ${i}")
                args.append(val)
                i += 1
            elif key == 'result':
                sets.append(f"result = ${i}::jsonb")
                args.append(json.dumps(val))
                i += 1
        if sets:
            sets.append("updated_at = now()")
            query = f"UPDATE pipeline_jobs SET {', '.join(sets)} WHERE book_id = ${i}"
            args.append(book_id)
            await self._ctx.db.execute(query, *args)

    async def get_job(self, book_id: str) -> dict | None:
        row = await self._ctx.db.fetch_one(
            "SELECT book_id, status, stage, error, result FROM pipeline_jobs WHERE book_id = $1",
            book_id,
        )
        if not row:
            return None
        result = dict(row)
        if result.get('result'):
            result.update(json.loads(result['result']))
            del result['result']
        return result

    async def close(self):
        if self._ctx:
            await self._ctx.close()


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------

# Paths that bypass authentication (health probes, status polling)
_PUBLIC_PATHS = frozenset({"/health"})
_PUBLIC_PREFIXES = ("/status/",)


def _extract_api_key(request: web.Request) -> str | None:
    """Extract API key from Authorization Bearer or X-API-Key header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.headers.get("X-API-Key", "").strip() or None


@web.middleware
async def api_key_middleware(request: web.Request, handler):
    """Enforce API key authentication on protected endpoints."""
    # Allow public paths through unconditionally
    path = request.path
    if path in _PUBLIC_PATHS or any(path.startswith(p) for p in _PUBLIC_PREFIXES):
        return await handler(request)

    configured_key: str = request.app["api_key"]

    # Permissive mode: no key configured → allow all requests
    if not configured_key:
        return await handler(request)

    provided_key = _extract_api_key(request)
    if not provided_key or not hmac.compare_digest(provided_key, configured_key):
        return web.json_response({"error": "Unauthorized"}, status=401)

    return await handler(request)


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
    job_tracker = request.app.get("job_tracker")
    if job_tracker and job_tracker._ctx:
        await job_tracker.create_job(book_id)
    
    # Fire-and-forget pipeline task
    asyncio.create_task(
        _run_pipeline_job(job_tracker, book_id, blob_uri, title, author, language, formats)
    )

    return web.json_response({"book_id": book_id, "status": "accepted"})


async def get_status(request: web.Request) -> web.Response:
    """Return pipeline status for a book."""
    book_id = request.match_info["book_id"]

    # Check persistent job tracker first
    job_tracker = request.app.get("job_tracker")
    if job_tracker and job_tracker._ctx:
        job = await job_tracker.get_job(book_id)
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
    job_tracker: JobTracker | None,
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

    if job_tracker and job_tracker._ctx:
        await job_tracker.update_job(book_id, status="running")

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

        if job_tracker and job_tracker._ctx:
            await job_tracker.update_job(
                book_id,
                status="completed",
                stage="export",
                result={
                    "book_id": str(output.book_id),
                    "stages_completed": output.stages_completed,
                    "glossary_terms": output.glossary_term_count,
                    "artifacts": output.artifacts,
                },
            )

    except Exception as exc:
        logger.exception(f"Pipeline failed for {book_id}")
        if job_tracker and job_tracker._ctx:
            await job_tracker.update_job(book_id, status="failed", error=str(exc))
    finally:
        with contextlib.suppress(Exception):
            await ctx.close()


# ---------------------------------------------------------------------------
# App factory & entrypoint
# ---------------------------------------------------------------------------


def create_app() -> web.Application:
    """Build the aiohttp application."""
    from transpose.config.settings import get_appinsights_connection_string
    from transpose.observability.tracing import configure_tracing

    configure_tracing(get_appinsights_connection_string())

    settings = get_settings()

    app = web.Application(middlewares=[api_key_middleware])
    app["api_key"] = settings.api_key
    app["job_tracker"] = JobTracker()

    if not settings.api_key:
        logger.warning(
            "TRANSPOSE_API_KEY is not set — API key authentication is DISABLED. "
            "Set TRANSPOSE_API_KEY for production deployments."
        )

    async def on_startup(app: web.Application) -> None:
        try:
            await app["job_tracker"].connect()
        except Exception:
            logger.warning("JobTracker DB connection unavailable — falling back to DB-less mode")

    async def on_cleanup(app: web.Application) -> None:
        try:
            await app["job_tracker"].close()
        except Exception:
            pass

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

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
