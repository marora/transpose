"""Tests for the PipelineState service."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from transpose.services.cache import PipelineState


class TestPipelineStateOperations:
    """Test PostgreSQL-backed pipeline state operations."""

    @pytest.mark.asyncio
    async def test_set_pipeline_status(self) -> None:
        """Test setting pipeline status."""
        book_id = str(uuid4())
        stage = "ocr"

        # Mock database
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        state = PipelineState(mock_db)
        await state.set_pipeline_status(book_id, stage)

        # Verify UPSERT query was called
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "INSERT INTO pipeline_state" in call_args[0][0]
        assert book_id in call_args[0]
        assert stage in call_args[0]

    @pytest.mark.asyncio
    async def test_get_pipeline_status(self) -> None:
        """Test getting pipeline status."""
        book_id = str(uuid4())
        expected_stage = "translate"

        # Mock database
        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"stage": expected_stage})

        state = PipelineState(mock_db)
        result = await state.get_pipeline_status(book_id)

        assert result == expected_stage
        mock_db.fetch_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_pipeline_status_not_found(self) -> None:
        """Test getting pipeline status when book doesn't exist."""
        book_id = str(uuid4())

        # Mock database returning None
        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value=None)

        state = PipelineState(mock_db)
        result = await state.get_pipeline_status(book_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_set_progress(self) -> None:
        """Test updating progress tracking."""
        book_id = str(uuid4())
        stage = "translate"
        completed = 50
        total = 100

        # Mock database
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        state = PipelineState(mock_db)
        await state.set_progress(book_id, stage, completed, total)

        # Verify UPDATE query was called
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "UPDATE pipeline_state" in call_args[0][0]
        assert book_id in call_args[0]


class TestPipelineStateLocking:
    """Test distributed locking with row-based TTL locks."""

    @pytest.mark.asyncio
    async def test_acquire_lock(self) -> None:
        """Test acquiring a distributed lock."""
        book_id = str(uuid4())

        # Mock database returning a row (lock acquired)
        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"book_id": book_id})

        state = PipelineState(mock_db)
        acquired = await state.acquire_lock(book_id)

        assert acquired is True
        mock_db.fetch_one.assert_called_once()
        call_args = mock_db.fetch_one.call_args
        assert "INSERT INTO pipeline_locks" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_lock_contention(self) -> None:
        """Test that lock cannot be acquired if already held."""
        book_id = str(uuid4())

        # Mock database returning None (lock already held, not expired)
        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value=None)

        state = PipelineState(mock_db)
        acquired = await state.acquire_lock(book_id)

        assert acquired is False

    @pytest.mark.asyncio
    async def test_release_lock(self) -> None:
        """Test releasing a lock."""
        book_id = str(uuid4())

        # Mock database
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock()

        state = PipelineState(mock_db)
        await state.release_lock(book_id)

        # Verify DELETE was called
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "DELETE FROM pipeline_locks" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_refresh_lock(self) -> None:
        """Test refreshing a lock TTL."""
        book_id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"book_id": book_id})

        state = PipelineState(mock_db)
        # First acquire to set holder_id
        await state.acquire_lock(book_id)
        mock_db.fetch_one.reset_mock()

        mock_db.fetch_one.return_value = {"book_id": book_id}
        refreshed = await state.refresh_lock(book_id)

        assert refreshed is True
        call_args = mock_db.fetch_one.call_args
        assert "UPDATE pipeline_locks" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_refresh_lock_without_holder(self) -> None:
        """Test that refresh fails without a prior acquire."""
        book_id = str(uuid4())

        mock_db = AsyncMock()
        state = PipelineState(mock_db)
        refreshed = await state.refresh_lock(book_id)

        assert refreshed is False
