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
    """Test distributed locking with PostgreSQL advisory locks."""

    @pytest.mark.asyncio
    async def test_acquire_lock(self) -> None:
        """Test acquiring a distributed lock."""
        book_id = str(uuid4())

        # Mock database returning True (lock acquired)
        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"pg_try_advisory_lock": True})

        state = PipelineState(mock_db)
        acquired = await state.acquire_lock(book_id)

        assert acquired is True
        mock_db.fetch_one.assert_called_once()
        call_args = mock_db.fetch_one.call_args
        assert "pg_try_advisory_lock" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_lock_contention(self) -> None:
        """Test that lock cannot be acquired if already held."""
        book_id = str(uuid4())

        # Mock database returning False (lock already held)
        mock_db = AsyncMock()
        mock_db.fetch_one = AsyncMock(return_value={"pg_try_advisory_lock": False})

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

        # Verify pg_advisory_unlock was called
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "pg_advisory_unlock" in call_args[0][0]
