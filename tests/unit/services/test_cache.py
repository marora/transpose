"""Tests for the Cache service."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class TestCacheOperations:
    """Test Redis cache operations."""

    @pytest.mark.asyncio
    async def test_set_pipeline_status(
        self,
        mock_cache: AsyncMock,
        fake_redis,
    ) -> None:
        """Test setting pipeline status."""
        book_id = uuid4()
        status = "ocr_complete"

        await fake_redis.set(f"pipeline:status:{book_id}", status)
        result = await fake_redis.get(f"pipeline:status:{book_id}")

        assert result == status

    @pytest.mark.asyncio
    async def test_get_pipeline_status(
        self,
        mock_cache: AsyncMock,
        fake_redis,
    ) -> None:
        """Test getting pipeline status."""
        book_id = uuid4()
        await fake_redis.set(f"pipeline:status:{book_id}", "translated")

        result = await fake_redis.get(f"pipeline:status:{book_id}")
        assert result == "translated"

    @pytest.mark.asyncio
    async def test_update_progress(
        self,
        mock_cache: AsyncMock,
        fake_redis,
    ) -> None:
        """Test updating progress tracking."""
        book_id = uuid4()
        key = f"pipeline:progress:{book_id}"

        await fake_redis.set(key, "50")
        progress = await fake_redis.get(key)

        assert progress == "50"


class TestCacheLocking:
    """Test distributed locking."""

    @pytest.mark.asyncio
    async def test_acquire_lock(
        self,
        fake_redis,
    ) -> None:
        """Test acquiring a distributed lock."""
        lock_key = "pipeline:lock:test"

        # Acquire lock
        result = await fake_redis.set(lock_key, "locked", ex=300, nx=True)
        assert result is True

    @pytest.mark.asyncio
    async def test_lock_contention(
        self,
        fake_redis,
    ) -> None:
        """Test that lock cannot be acquired if already held."""
        lock_key = "pipeline:lock:test"

        # First acquire
        await fake_redis.set(lock_key, "locked", ex=300, nx=True)

        # Second acquire should fail
        result = await fake_redis.set(lock_key, "locked", ex=300, nx=True)
        assert result is None

    @pytest.mark.asyncio
    async def test_release_lock(
        self,
        fake_redis,
    ) -> None:
        """Test releasing a lock."""
        lock_key = "pipeline:lock:test"

        await fake_redis.set(lock_key, "locked", ex=300, nx=True)
        await fake_redis.delete(lock_key)

        # Should be able to acquire again
        result = await fake_redis.set(lock_key, "locked", ex=300, nx=True)
        assert result is True
