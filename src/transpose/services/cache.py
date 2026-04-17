"""Redis connection and pipeline state helpers."""

from __future__ import annotations

import redis.asyncio as redis


class Cache:
    """Async Redis client for pipeline state and caching.

    Handles:
    - Pipeline progress tracking (pipeline:{book_id}:status, :progress)
    - Distributed locks (pipeline:{book_id}:lock)
    - Chunk caching
    - Rate limit counters
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        """Initialize the Redis connection."""
        self._client = redis.from_url(self._url, decode_responses=True)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.close()

    @property
    def client(self) -> redis.Redis:
        """Access the Redis client. Raises if not connected."""
        if self._client is None:
            raise RuntimeError("Cache not connected. Call connect() first.")
        return self._client

    async def set_pipeline_status(self, book_id: str, stage: str) -> None:
        """Update the current pipeline stage for a book."""
        await self.client.set(f"pipeline:{book_id}:status", stage)

    async def get_pipeline_status(self, book_id: str) -> str | None:
        """Get the current pipeline stage for a book."""
        return await self.client.get(f"pipeline:{book_id}:status")

    async def set_progress(self, book_id: str, stage: str, completed: int, total: int) -> None:
        """Update progress within a stage."""
        import json

        await self.client.set(
            f"pipeline:{book_id}:progress",
            json.dumps({"stage": stage, "completed": completed, "total": total}),
        )

    async def acquire_lock(self, book_id: str, ttl: int = 3600) -> bool:
        """Acquire a distributed lock for a book. Returns True if acquired."""
        return bool(await self.client.set(f"pipeline:{book_id}:lock", "1", nx=True, ex=ttl))

    async def release_lock(self, book_id: str) -> None:
        """Release the distributed lock for a book."""
        await self.client.delete(f"pipeline:{book_id}:lock")
