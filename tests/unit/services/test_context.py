"""Tests for transpose.services.context — ServiceContext lifecycle.

Covers:
- Initialization with explicit settings (no .env leak)
- DSN construction (with and without password)
- SSL detection for Azure PostgreSQL
- connect() and close() lifecycle
- All sub-services are initialized
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock

import pytest

from transpose.config.settings import Settings
from transpose.services.context import ServiceContext


def _test_settings(**overrides) -> Settings:
    """Settings that don't read .env."""
    defaults = {
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "postgres_db": "testdb",
        "postgres_user": "testuser",
        "postgres_password": "",
        "doc_intelligence_endpoint": "https://di.cognitiveservices.azure.com",
        "openai_endpoint": "https://oai.openai.azure.com",
        "openai_deployment": "gpt-4o",
        "openai_api_version": "2024-10-21",
        "blob_storage_account_url": "https://storage.blob.core.windows.net",
    }
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestServiceContextInit:
    def test_all_services_created(self) -> None:
        """ServiceContext creates all sub-services on init."""
        # Strip TRANSPOSE_ env vars to prevent .env leakage
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(settings=_test_settings())
            assert ctx.db is not None
            assert ctx.state is not None
            assert ctx.blob is not None
            assert ctx.ocr is not None
            assert ctx.llm is not None
        finally:
            os.environ.update(saved)

    def test_settings_stored(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            settings = _test_settings()
            ctx = ServiceContext(settings=settings)
            assert ctx.settings is settings
        finally:
            os.environ.update(saved)


# ---------------------------------------------------------------------------
# DSN construction
# ---------------------------------------------------------------------------


class TestDSNConstruction:
    def test_dsn_without_password(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(settings=_test_settings(postgres_password=""))
            dsn = ctx._build_dsn()
            assert "testuser@localhost" in dsn
            assert "testdb" in dsn
            assert ":@" not in dsn  # no password separator
        finally:
            os.environ.update(saved)

    def test_dsn_with_password(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(settings=_test_settings(postgres_password="secret"))
            dsn = ctx._build_dsn()
            assert "testuser:secret@localhost" in dsn
        finally:
            os.environ.update(saved)

    def test_dsn_port_included(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(settings=_test_settings(postgres_port=5433))
            dsn = ctx._build_dsn()
            assert ":5433/" in dsn
        finally:
            os.environ.update(saved)


# ---------------------------------------------------------------------------
# SSL detection
# ---------------------------------------------------------------------------


class TestSSLDetection:
    def test_azure_host_requires_ssl(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(
                settings=_test_settings(postgres_host="myserver.database.azure.com")
            )
            assert ctx._requires_ssl is True
        finally:
            os.environ.update(saved)

    def test_localhost_no_ssl(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(settings=_test_settings(postgres_host="localhost"))
            assert ctx._requires_ssl is False
        finally:
            os.environ.update(saved)


# ---------------------------------------------------------------------------
# connect / close lifecycle
# ---------------------------------------------------------------------------


class TestServiceContextLifecycle:
    @pytest.mark.asyncio
    async def test_connect_calls_db_connect(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(settings=_test_settings())
            ctx.db = AsyncMock()
            ctx.state = AsyncMock()

            await ctx.connect()

            ctx.db.connect.assert_called_once()
            ctx.state.ensure_lock_table.assert_called_once()
        finally:
            os.environ.update(saved)

    @pytest.mark.asyncio
    async def test_connect_with_azure_ssl(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(
                settings=_test_settings(postgres_host="myserver.database.azure.com")
            )
            ctx.db = AsyncMock()
            ctx.state = AsyncMock()

            await ctx.connect()

            ctx.db.connect.assert_called_once_with(ssl="require")
        finally:
            os.environ.update(saved)

    @pytest.mark.asyncio
    async def test_close_closes_all_services(self) -> None:
        saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("TRANSPOSE_")}
        try:
            ctx = ServiceContext(settings=_test_settings())
            ctx.db = AsyncMock()
            ctx.blob = AsyncMock()
            ctx.ocr = AsyncMock()
            ctx.llm = AsyncMock()

            await ctx.close()

            ctx.db.close.assert_called_once()
            ctx.blob.close.assert_called_once()
            ctx.ocr.close.assert_called_once()
            ctx.llm.close.assert_called_once()
        finally:
            os.environ.update(saved)
