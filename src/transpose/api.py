"""Minimal HTTP API for Transpose Container App health and trigger endpoints."""

from __future__ import annotations

import logging
import os

from aiohttp import web

logger = logging.getLogger(__name__)


async def health(_request: web.Request) -> web.Response:
    """Health check endpoint for Container Apps probes."""
    return web.json_response({"status": "ok", "service": "transpose"})


async def root(_request: web.Request) -> web.Response:
    """Root endpoint."""
    return web.json_response({"service": "transpose", "version": "0.1.0"})


def create_app() -> web.Application:
    """Create the aiohttp application."""
    app = web.Application()
    app.router.add_get("/", root)
    app.router.add_get("/health", health)
    return app


def main() -> None:
    """Run the HTTP server."""
    port = int(os.environ.get("PORT", "8000"))
    app = create_app()
    logger.info("Starting Transpose API on port %d", port)
    web.run_app(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
