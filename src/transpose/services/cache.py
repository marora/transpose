"""PostgreSQL-backed pipeline state management."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from transpose.services.database import Database


class PipelineState:
    """PostgreSQL-backed pipeline state tracker.

    Handles:
    - Pipeline progress tracking (pipeline_state table)
    - Distributed locks (pg_try_advisory_lock)
    - Stage status updates
    - Progress tracking within stages
    """

    def __init__(self, db: Database) -> None:
        """Initialize with a Database instance."""
        self._db = db

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
        """Acquire a distributed lock for a book using PostgreSQL advisory locks.

        Returns True if acquired, False if already held.
        """
        # Use hashtext to convert book_id string to integer for advisory lock
        query = "SELECT pg_try_advisory_lock(hashtext($1))"
        row = await self._db.fetch_one(query, book_id)
        return bool(row["pg_try_advisory_lock"]) if row else False

    async def release_lock(self, book_id: str) -> None:
        """Release the distributed lock for a book."""
        query = "SELECT pg_advisory_unlock(hashtext($1))"
        await self._db.execute(query, book_id)
