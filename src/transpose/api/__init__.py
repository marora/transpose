"""Lightweight HTTP API for triggering the Transpose pipeline.

Designed for Azure Container Apps deployment. Runs on port 8000.

Endpoints:
    GET  /health            → deep health check (liveness — always 200)
    GET  /ready             → readiness probe (503 when degraded)
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
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from aiohttp import web

from transpose.api.auth.entra_middleware import (
    EntraTokenValidator,
    entra_admin_middleware,
    is_admin_path,
)
from transpose.config.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Per-check timeout for health probes (seconds)
_HEALTH_CHECK_TIMEOUT = 3.0


class JobTracker:
    """PostgreSQL-backed job status tracker."""

    def __init__(self):
        self._ctx = None
        self._background_tasks: set[asyncio.Task] = set()

    async def connect(self):
        """Initialize database connection.

        On failure, leaves ``self._ctx`` as ``None`` so callers can detect
        DB-less mode via the ``if job_tracker._ctx`` guard pattern used
        throughout the API.
        """
        from transpose.services import ServiceContext

        ctx = ServiceContext()
        try:
            await ctx.connect()
            # Ensure jobs table exists
            await ctx.db.execute("""
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
        except Exception:
            # Ensure partially-initialized context is not retained so the
            # DB-less fallback guard (`if job_tracker._ctx`) works correctly.
            with contextlib.suppress(Exception):
                await ctx.close()
            self._ctx = None
            raise
        self._ctx = ctx

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
# Health checks
# ---------------------------------------------------------------------------


async def _check_database(app: web.Application) -> str:
    """Verify PostgreSQL connectivity with a simple query."""
    job_tracker: JobTracker | None = app.get("job_tracker")
    if not job_tracker or not job_tracker._ctx:
        return "not_configured"
    try:
        row = await asyncio.wait_for(
            job_tracker._ctx.db.fetch_one("SELECT 1 AS ok"),
            timeout=_HEALTH_CHECK_TIMEOUT,
        )
        return "ok" if row else "error: empty result"
    except TimeoutError:
        return "error: timeout"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


async def _check_blob(app: web.Application) -> str:
    """Verify Azure Blob Storage connectivity by listing container properties."""
    settings = get_settings()
    if not settings.blob_storage_account_url:
        return "not_configured"
    try:
        from azure.identity.aio import DefaultAzureCredential
        from azure.storage.blob.aio import BlobServiceClient

        async def _probe():
            credential = DefaultAzureCredential()
            try:
                client = BlobServiceClient(
                    account_url=settings.blob_storage_account_url,
                    credential=credential,
                )
                try:
                    await client.get_account_information()
                    return "ok"
                finally:
                    await client.close()
            finally:
                await credential.close()

        return await asyncio.wait_for(_probe(), timeout=_HEALTH_CHECK_TIMEOUT)
    except TimeoutError:
        return "error: timeout"
    except ImportError:
        return "not_configured"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


async def _check_openai(app: web.Application) -> str:
    """Verify Azure OpenAI connectivity with a lightweight models list."""
    settings = get_settings()
    if not settings.openai_endpoint:
        return "not_configured"
    try:
        import httpx

        async def _probe():
            url = (
                f"{settings.openai_endpoint.rstrip('/')}"
                f"/openai/models?api-version={settings.openai_api_version}"
            )
            from azure.identity.aio import DefaultAzureCredential

            credential = DefaultAzureCredential()
            try:
                token = await credential.get_token("https://cognitiveservices.azure.com/.default")
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        url,
                        headers={"Authorization": f"Bearer {token.token}"},
                        timeout=_HEALTH_CHECK_TIMEOUT,
                    )
                    if resp.status_code < 400:
                        return "ok"
                    return f"error: HTTP {resp.status_code}"
            finally:
                await credential.close()

        return await asyncio.wait_for(_probe(), timeout=_HEALTH_CHECK_TIMEOUT)
    except TimeoutError:
        return "error: timeout"
    except ImportError:
        return "not_configured"
    except Exception as exc:
        return f"error: {type(exc).__name__}"


async def _run_health_checks(app: web.Application) -> dict:
    """Run all health checks concurrently and return structured result."""
    db_check, blob_check, openai_check = await asyncio.gather(
        _check_database(app),
        _check_blob(app),
        _check_openai(app),
        return_exceptions=True,
    )

    # Normalise gather exceptions
    checks = {}
    for name, result in [("database", db_check), ("blob", blob_check), ("openai", openai_check)]:
        if isinstance(result, BaseException):
            checks[name] = f"error: {type(result).__name__}"
        else:
            checks[name] = result

    # Determine overall status
    errors = [v for v in checks.values() if v.startswith("error:")]
    status = ("degraded" if len(errors) < len(checks) else "unhealthy") if errors else "healthy"

    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# API Key Authentication
# ---------------------------------------------------------------------------

# Paths that bypass API key authentication (health probes, status polling, Entra admin routes)
_PUBLIC_PATHS = frozenset({"/health", "/ready"})
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
    is_public_path = (
        path in _PUBLIC_PATHS
        or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)
    )
    if is_public_path or is_admin_path(path):
        return await handler(request)

    configured_key: str = request.app["api_key"]

    # Permissive mode: no key configured → allow all requests
    if not configured_key:
        return await handler(request)

    provided_key = _extract_api_key(request)
    if not provided_key or not hmac.compare_digest(provided_key, configured_key):
        return _error_response("Unauthorized", code="UNAUTHORIZED", status=401, request=request)

    return await handler(request)


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------


@web.middleware
async def request_id_middleware(request: web.Request, handler):
    """Attach a unique request ID to every request/response for correlation."""
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request["request_id"] = request_id
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        exc.headers["X-Request-ID"] = request_id
        raise
    except Exception:
        raise
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Structured error helpers
# ---------------------------------------------------------------------------


def _error_response(
    message: str,
    *,
    code: str = "INTERNAL_ERROR",
    status: int = 500,
    details: list | None = None,
    request: web.Request | None = None,
) -> web.Response:
    """Build a structured JSON error response."""
    request_id = request.get("request_id", "unknown") if request else "unknown"
    body = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        }
    }
    if details:
        body["error"]["details"] = details
    return web.json_response(body, status=status)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def health(request: web.Request) -> web.Response:
    """Liveness probe — always returns 200, reports deep check results."""
    result = await _run_health_checks(request.app)
    return web.json_response(result, status=200)


async def ready(request: web.Request) -> web.Response:
    """Readiness probe — returns 503 when any check is degraded/unhealthy."""
    result = await _run_health_checks(request.app)
    status = 200 if result["status"] == "healthy" else 503
    return web.json_response(result, status=status)


_ADMIN_ROOT = Path(__file__).resolve().parents[3] / "web" / "admin"


async def admin_index(request: web.Request) -> web.StreamResponse:
    """Serve the protected admin dashboard shell."""
    return web.FileResponse(_ADMIN_ROOT / "index.html")


async def admin_auth_smoke(request: web.Request) -> web.Response:
    """Return the authenticated principal for smoke testing /admin protection."""
    return web.json_response({"status": "ok", "user": request["user"]})


async def translate(request: web.Request) -> web.Response:
    """Accept a translation request and run the pipeline in background."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, Exception):
        return _error_response(
            "invalid JSON body",
            code="INVALID_JSON",
            status=400,
            request=request,
        )

    # Validate required fields
    blob_uri = body.get("blob_uri")
    title = body.get("title")
    if not blob_uri or not title:
        return _error_response(
            "blob_uri and title are required",
            code="MISSING_FIELDS",
            status=400,
            details=["blob_uri and title are required fields"],
            request=request,
        )

    language = body.get("language", "hindi")
    if language not in ("hindi", "punjabi"):
        return _error_response(
            "language must be 'hindi' or 'punjabi'",
            code="INVALID_LANGUAGE",
            status=400,
            request=request,
        )

    author = body.get("author")
    formats = body.get("formats", ["epub", "pdf"])

    book_id = str(uuid4())
    job_tracker = request.app.get("job_tracker")
    if job_tracker and job_tracker._ctx:
        await job_tracker.create_job(book_id)

    concurrency = body.get("concurrency")
    if concurrency is not None and (not isinstance(concurrency, int) or concurrency < 1):
        return web.json_response(
            {"error": "concurrency must be a positive integer"},
            status=400,
        )

    # Launch pipeline task with proper lifecycle management
    task = asyncio.create_task(
        _run_pipeline_job(
            job_tracker,
            book_id,
            blob_uri,
            title,
            author,
            language,
            formats,
            concurrency,
        )
    )
    # Prevent GC collection and log failures
    if job_tracker:
        job_tracker._background_tasks.add(task)
        task.add_done_callback(lambda t: _on_task_done(t, book_id, job_tracker))
    else:
        task.add_done_callback(lambda t: _on_task_done(t, book_id, None))

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
        return _error_response(
            "invalid book_id format", code="INVALID_BOOK_ID", status=400, request=request,
        )

    try:
        from transpose.services import ServiceContext

        ctx = ServiceContext()
        await ctx.connect()
        try:
            book = await ctx.db.get_book(UUID(book_id))
            if not book:
                return _error_response(
                    "book not found", code="NOT_FOUND", status=404, request=request,
                )
            return web.json_response({
                "book_id": book_id,
                "status": str(book.status),
                "title": book.title,
                "page_count": book.page_count,
            })
        finally:
            await ctx.close()
    except Exception:
        request_id = request.get("request_id", "unknown")
        logger.exception("Error fetching status from DB [request_id=%s]", request_id)
        return _error_response(
            "internal error fetching status",
            code="INTERNAL_ERROR",
            status=500,
            request=request,
        )


# ---------------------------------------------------------------------------
# Background pipeline runner
# ---------------------------------------------------------------------------


def _on_task_done(task: asyncio.Task, book_id: str, job_tracker: JobTracker | None) -> None:
    """Callback for completed pipeline tasks — logs errors, cleans up references."""
    if job_tracker:
        job_tracker._background_tasks.discard(task)

    if task.cancelled():
        logger.warning("Pipeline task cancelled for book_id=%s", book_id)
        return

    exc = task.exception()
    if exc:
        logger.error(
            "Pipeline task failed for book_id=%s: %s: %s",
            book_id, type(exc).__name__, exc,
        )
    else:
        logger.info("Pipeline task completed for book_id=%s", book_id)


async def _run_pipeline_job(
    job_tracker: JobTracker | None,
    book_id: str,
    blob_uri: str,
    title: str,
    author: str | None,
    language: str,
    formats: list[str],
    concurrency: int | None = None,
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
            concurrency=concurrency,
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
# Global exception handler
# ---------------------------------------------------------------------------


@web.middleware
async def _json_error_handler(request: web.Request, handler):
    """Catch unhandled exceptions and return structured JSON errors."""
    try:
        return await handler(request)
    except web.HTTPException:
        raise  # Let aiohttp handle HTTP errors normally
    except ValueError as exc:
        request_id = request.get("request_id", "unknown")
        logger.warning("ValueError [request_id=%s]: %s", request_id, exc)
        return _error_response(
            str(exc), code="VALIDATION_ERROR", status=400, request=request,
        )
    except Exception as exc:
        request_id = request.get("request_id", "unknown")
        logger.exception("Unhandled exception [request_id=%s]", request_id)
        settings = get_settings()
        # Only expose detail in debug mode (non-production, no API key configured)
        message = str(exc) if not settings.api_key else "internal server error"
        return _error_response(
            message, code="INTERNAL_ERROR", status=500, request=request,
        )


# ---------------------------------------------------------------------------
# App factory & entrypoint
# ---------------------------------------------------------------------------


def create_app() -> web.Application:
    """Build the aiohttp application."""
    from transpose.config.settings import get_appinsights_connection_string
    from transpose.observability.tracing import configure_tracing

    configure_tracing(get_appinsights_connection_string())

    settings = get_settings()

    app = web.Application(middlewares=[
        request_id_middleware,
        entra_admin_middleware,
        api_key_middleware,
        _json_error_handler,
    ])
    app["settings"] = settings
    app["api_key"] = settings.api_key
    app["job_tracker"] = JobTracker()
    app["entra_authority"] = settings.get_entra_authority_url()
    if settings.entra_admin_auth_configured:
        app["entra_token_validator"] = EntraTokenValidator(settings)

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
        with contextlib.suppress(Exception):
            await app["job_tracker"].close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    app.router.add_get("/health", health)
    app.router.add_get("/ready", ready)
    app.router.add_post("/translate", translate)
    app.router.add_get("/status/{book_id}", get_status)
    app.router.add_get("/admin", admin_index)
    app.router.add_get("/admin/", admin_index)
    app.router.add_get("/admin/index.html", admin_index)
    app.router.add_get("/admin/api/test", admin_auth_smoke)
    from transpose.api.dashboard import register_dashboard_routes
    register_dashboard_routes(app)
    app.router.add_static("/admin/", path=_ADMIN_ROOT, show_index=False)
    return app


def main() -> None:
    """Run the HTTP server on port 8000."""
    port = int(os.environ.get("PORT", "8000"))
    logger.info(f"Starting Transpose API on port {port}")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
