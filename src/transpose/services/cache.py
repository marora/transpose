"""PostgreSQL-backed pipeline state management."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from transpose.services.database import Database


class PipelineState:
    """PostgreSQL-backed pipeline state tracker.

    Handles:
    - Pipeline progress tracking (pipeline_state table)
    - Distributed locks with TTL (pipeline_locks table)
    - Stage status updates
    - Progress tracking within stages
    """

    def __init__(self, db: Database) -> None:
        """Initialize with a Database instance."""
        self._db = db
        self._holder_id: str | None = None

    async def ensure_lock_table(self) -> None:
        """Create the pipeline_locks table if it does not exist."""
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_locks (
                book_id TEXT PRIMARY KEY,
                locked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                expires_at TIMESTAMPTZ NOT NULL,
                holder_id TEXT NOT NULL
            )
        """)

    async def set_pipeline_status(self, book_id: str, stage: str) -> None:
        """Update the current pipeline stage for a book."""
        query = """
            INSERT INTO pipeline_state (book_id, stage, status, updated_at)
            VALUES ($1, $2, 'running', now())
            ON CONFLICT (book_id)
            DO UPDATE SET
                stage = EXCLUDED.stage,
                status = 'running',
                updated_at = now()
        """
        await self._db.execute(query, book_id, stage)

    async def get_pipeline_status(self, book_id: str) -> str | None:
        """Get the current pipeline stage for a book."""
        query = "SELECT stage FROM pipeline_state WHERE book_id = $1"
        row = await self._db.fetch_one(query, book_id)
        return row["stage"] if row else None

    async def set_progress(self, book_id: str, stage: str, completed: int, total: int) -> None:
        """Update progress within a stage."""
        query = """
            UPDATE pipeline_state
            SET progress_completed = $2,
                progress_total = $3,
                updated_at = now()
            WHERE book_id = $1
        """
        await self._db.execute(query, book_id, completed, total)

    async def acquire_lock(self, book_id: str, ttl: int = 3600) -> bool:
        """Acquire a distributed lock for a book with TTL enforcement.

        Uses row-based locking with expiration timestamps.
        Stale locks (past TTL) are automatically reclaimed.
        Returns True if acquired, False if already held by an active session.
        """
        query = """
            INSERT INTO pipeline_locks (book_id, locked_at, expires_at, holder_id)
            VALUES ($1, now(), now() + ($2 || ' seconds')::interval, $3)
            ON CONFLICT (book_id) DO UPDATE
            SET locked_at = now(),
                expires_at = now() + ($2 || ' seconds')::interval,
                holder_id = $3
            WHERE pipeline_locks.expires_at < now()  -- only reclaim expired locks
            RETURNING book_id
        """
        if self._holder_id is None:
            self._holder_id = str(uuid.uuid4())
        row = await self._db.fetch_one(query, book_id, str(ttl), self._holder_id)
        return row is not None

    async def release_lock(self, book_id: str) -> None:
        """Release the distributed lock for a book."""
        query = "DELETE FROM pipeline_locks WHERE book_id = $1"
        await self._db.execute(query, book_id)

    async def refresh_lock(self, book_id: str, ttl: int = 3600) -> bool:
        """Refresh the TTL on an existing lock. Returns True if refreshed."""
        if not self._holder_id:
            return False
        query = """
            UPDATE pipeline_locks
            SET expires_at = now() + ($2 || ' seconds')::interval,
                locked_at = now()
            WHERE book_id = $1 AND holder_id = $3
            RETURNING book_id
        """
        row = await self._db.fetch_one(query, book_id, str(ttl), self._holder_id)
        return row is not None
