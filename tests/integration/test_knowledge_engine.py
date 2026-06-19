"""
Integration tests for the Knowledge Engine service.

These tests spin up the FastAPI app with pytest-asyncio + httpx.AsyncClient,
mocking out external infrastructure (Qdrant, Neo4j, PostgreSQL, Anthropic)
so they run in CI without real services.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, AsyncGenerator, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def mock_db_pool():
    """Return a mock asyncpg pool that silently accepts all SQL calls."""
    pool = AsyncMock()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn),
                                                     __aexit__=AsyncMock(return_value=False)))
    return pool


@pytest_asyncio.fixture
async def mock_retrieve_handler():
    """Return a mock RetrieveContextHandler that returns two fake chunks."""
    handler = AsyncMock()

    class FakeChunk:
        text     = "Pump P-101 requires lubrication every 500 hours."
        score    = 0.92
        doc_id   = "doc-001"
        metadata = {"source": "maintenance_manual", "page": 12}

    handler.handle = AsyncMock(return_value=[FakeChunk(), FakeChunk()])
    return handler


@pytest_asyncio.fixture
async def mock_orchestrator():
    """Return a mock AgentOrchestrator with a predictable response."""
    orch = AsyncMock()

    class FakeResult:
        def model_dump(self):
            return {
                "answer": "Root cause: bearing wear on shaft A.",
                "confidence": 0.85,
                "sources": [],
                "reasoning_steps": ["Telemetry retrieved.", "Knowledge queried."],
                "recommended_actions": ["Replace bearing.", "Increase lubrication schedule."],
            }

    orch.route_and_execute = AsyncMock(return_value=FakeResult())
    return orch


@pytest_asyncio.fixture
async def mock_ingest_handler():
    """Return a mock IngestDocumentHandler."""
    handler = AsyncMock()
    handler.handle = AsyncMock(return_value=None)
    return handler


@pytest_asyncio.fixture
async def app_client(mock_db_pool, mock_retrieve_handler, mock_orchestrator, mock_ingest_handler) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an AsyncClient for the Knowledge Engine app with all singletons
    pre-loaded into app.state — no real infrastructure needed.
    """
    # Patch lifespan so the app doesn't try to connect to real services
    from backend.services.knowledge_engine.main import app

    # Inject mocked singletons directly into app.state before the client starts
    app.state.db_pool          = mock_db_pool
    app.state.retrieve_handler = mock_retrieve_handler
    app.state.ingest_handler   = mock_ingest_handler
    app.state.orchestrator     = mock_orchestrator

    # Patch the get_db_pool dependency to return our mock pool
    from backend.shared.infrastructure.database.postgres import get_db_pool

    async def _override_pool():
        yield mock_db_pool

    app.dependency_overrides[get_db_pool] = _override_pool

    # Patch Kafka consumer so it doesn't connect in tests
    with patch("backend.services.knowledge_engine.main._kafka_agent_task_consumer", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

    app.dependency_overrides.clear()


# ── Health endpoint ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_returns_healthy(app_client: AsyncClient) -> None:
    resp = await app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["service"] == "knowledge_engine"


# ── RAG retrieval endpoint ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rag_retrieve_returns_chunks(app_client: AsyncClient) -> None:
    payload = {
        "query":      "How often should pump P-101 be lubricated?",
        "tenant_id":  "test-tenant",
        "top_k":      2,
    }
    resp = await app_client.post("/api/v1/rag/retrieve", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["chunks"]) == 2
    assert "Pump P-101" in data["chunks"][0]["text"]
    assert data["query"] == payload["query"]


@pytest.mark.asyncio
async def test_rag_retrieve_503_when_handler_missing(app_client: AsyncClient) -> None:
    """If retrieve_handler is not in app.state, endpoint must return 503."""
    del app_client.app.state.retrieve_handler          # type: ignore[attr-defined]
    resp = await app_client.post(
        "/api/v1/rag/retrieve",
        json={"query": "test", "tenant_id": "t1"},
    )
    assert resp.status_code == 503
    # Restore
    from backend.services.knowledge_engine.main import app
    app.state.retrieve_handler = (await anext(aiter([]))) if False else None  # will be re-injected by fixture


# ── Agent task endpoints ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_analysis_task_returns_task_id(app_client: AsyncClient) -> None:
    payload = {
        "session_id": "sess-001",
        "tenant_id":  "test-tenant",
        "query":      "Diagnose vibration anomaly on machine CNC-07.",
        "task_type":  "rca",
    }
    resp = await app_client.post("/api/v1/agents/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "processing"
    # Validate task_id is a valid UUID
    uuid.UUID(data["task_id"])


@pytest.mark.asyncio
async def test_get_task_status_not_found(app_client: AsyncClient) -> None:
    """A task that doesn't exist should return 404."""
    resp = await app_client.get(f"/api/v1/agents/tasks/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_task_trace_not_found(app_client: AsyncClient) -> None:
    resp = await app_client.get(f"/api/v1/agents/tasks/{uuid.uuid4()}/trace")
    assert resp.status_code == 404


# ── Ingestion endpoint ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_document_returns_job_id(app_client: AsyncClient) -> None:
    content = b"%PDF-1.4 fake pdf content for testing"
    resp = await app_client.post(
        "/api/v1/ingest/document",
        files={"file": ("test_manual.pdf", content, "application/pdf")},
        data={"tenant_id": "test-tenant", "factory_id": "factory-01", "doc_type": "manual"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "processing"
    assert data["filename"] == "test_manual.pdf"
    uuid.UUID(data["job_id"])


@pytest.mark.asyncio
async def test_ingest_get_job_not_found(app_client: AsyncClient) -> None:
    resp = await app_client.get(f"/api/v1/ingest/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
