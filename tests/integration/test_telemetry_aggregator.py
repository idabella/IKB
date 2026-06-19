"""
Integration tests for the Telemetry Aggregator service.
"""
from __future__ import annotations

import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def mock_db_pool():
    pool = AsyncMock()
    conn = AsyncMock()
    conn.execute  = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch    = AsyncMock(return_value=[])
    pool.acquire  = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=conn),
            __aexit__=AsyncMock(return_value=False),
        )
    )
    return pool


@pytest_asyncio.fixture
async def mock_stream_processor(mock_db_pool):
    proc = AsyncMock()
    proc.influx_client = AsyncMock()
    proc.influx_client.write_batch = AsyncMock(return_value=None)
    proc.redis_cache = AsyncMock()
    proc.redis_cache.get_latest = AsyncMock(return_value=[
        {"sensor_id": "s-01", "value": 42.5, "timestamp": 1700000000.0},
    ])
    proc.db_pool = mock_db_pool
    return proc


@pytest_asyncio.fixture
async def app_client(mock_db_pool, mock_stream_processor) -> AsyncGenerator[AsyncClient, None]:
    from backend.services.telemetry_aggregator.main import app
    from backend.shared.infrastructure.database.postgres import get_db_pool

    app.state.db_pool        = mock_db_pool
    app.state.stream_processor = mock_stream_processor

    async def _override_pool():
        yield mock_db_pool

    app.dependency_overrides[get_db_pool] = _override_pool

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── Health ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_healthy(app_client: AsyncClient) -> None:
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "telemetry_aggregator"


# ── Sensors ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_latest_readings(app_client: AsyncClient) -> None:
    resp = await app_client.get("/api/v1/sensors/machines/CNC-07/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["machine_id"] == "CNC-07"
    assert data["count"] == 1
    assert data["readings"][0]["value"] == 42.5


@pytest.mark.asyncio
async def test_ingest_sensor_reading(app_client: AsyncClient) -> None:
    payload = {
        "sensor_id":  "temp-01",
        "machine_id": "CNC-07",
        "value":      75.3,
        "unit":       "°C",
    }
    resp = await app_client.post("/api/v1/sensors/readings", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["sensor_id"] == "temp-01"
    assert data["value"] == 75.3
    assert "received_at" in data


# ── Anomalies ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_anomalies_empty(app_client: AsyncClient) -> None:
    """Returns an empty list when no anomalies exist."""
    resp = await app_client.get("/api/v1/anomalies/machines/CNC-07")
    assert resp.status_code == 200
    data = resp.json()
    assert data["machine_id"] == "CNC-07"
    assert data["anomalies"] == []
    assert data["count"] == 0


@pytest.mark.asyncio
async def test_get_anomaly_not_found(app_client: AsyncClient) -> None:
    resp = await app_client.get(f"/api/v1/anomalies/{uuid.uuid4()}")
    assert resp.status_code == 404
