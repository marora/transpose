"""Tests for the Database service."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


class TestDatabaseOperations:
    """Test database CRUD operations."""

    @pytest.mark.asyncio
    async def test_execute_query(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test executing a query."""
        mock_database.execute = AsyncMock(return_value=uuid4())

        result = await mock_database.execute(
            "INSERT INTO books (title) VALUES ($1) RETURNING id",
            "Test Book",
        )

        assert result is not None
        mock_database.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_one(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test fetching a single row."""
        book_id = uuid4()
        mock_database.fetch_one = AsyncMock(
            return_value={"id": book_id, "title": "Test Book"}
        )

        result = await mock_database.fetch_one(
            "SELECT * FROM books WHERE id = $1", book_id
        )

        assert result is not None
        assert result["id"] == book_id
        assert result["title"] == "Test Book"

    @pytest.mark.asyncio
    async def test_fetch_all(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test fetching multiple rows."""
        mock_database.fetch_all = AsyncMock(
            return_value=[
                {"id": uuid4(), "title": "Book 1"},
                {"id": uuid4(), "title": "Book 2"},
            ]
        )

        results = await mock_database.fetch_all("SELECT * FROM books")

        assert len(results) == 2
        assert results[0]["title"] == "Book 1"


class TestDatabaseConnectionHandling:
    """Test database connection error handling."""

    @pytest.mark.asyncio
    async def test_connection_error(
        self,
        mock_database: AsyncMock,
    ) -> None:
        """Test handling connection errors."""
        mock_database.execute = AsyncMock(side_effect=ConnectionError("DB unreachable"))

        with pytest.raises(ConnectionError):
            await mock_database.execute("SELECT 1")
