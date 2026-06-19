"""
Shared pytest fixtures used across unit and integration test suites.
"""
from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def fake_chunk():
    """A single fake RAG result chunk."""
    class FakeChunk:
        text     = "Bearing replacement interval: every 6 months or 2000 operating hours."
        score    = 0.95
        doc_id   = "doc-maintenance-001"
        metadata = {"page": 4, "source": "pump_manual_2023.pdf"}
    return FakeChunk()


@pytest.fixture
def mock_retrieve_handler(fake_chunk):
    """RetrieveContextHandler mock that returns one chunk."""
    handler = AsyncMock()
    handler.handle = AsyncMock(return_value=[fake_chunk])
    return handler


@pytest.fixture
def mock_db_conn():
    """Minimal asyncpg connection mock."""
    conn = AsyncMock()
    conn.execute  = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch    = AsyncMock(return_value=[])
    return conn


@pytest.fixture
def mock_db_pool(mock_db_conn):
    """asyncpg Pool mock that returns mock_db_conn from acquire()."""
    pool = AsyncMock()
    pool.acquire = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_db_conn),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return pool
