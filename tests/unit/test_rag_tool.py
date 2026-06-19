"""
Unit tests for RagTool.

Tests verify both execution paths:
  - Path A (in-process): inject retrieve_handler → direct call, no HTTP
  - Path B (legacy HTTP): inject rag_client → deprecated HTTP fallback
  - Error cases: neither handler configured, bad responses, missing query
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.agent_service.src.infrastructure.tools.rag_tool import RagTool


# ── Helpers ───────────────────────────────────────────────────────────────────

class FakeChunk:
    text     = "Lubrication interval is 500 operating hours."
    score    = 0.91
    doc_id   = "doc-001"
    metadata = {"page": 7, "source": "pump_manual.pdf"}


class FakeResult:
    """Simulates the ToolResult returned by BaseTool.execute()."""
    def __init__(self, success: bool, data: Any = None, error: str = None):
        self.success = success
        self.data    = data
        self.error   = error


# ── Path A: In-process retrieve_handler ──────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_inprocess_returns_chunks():
    """RagTool with retrieve_handler should call it directly, no HTTP."""
    handler = AsyncMock()
    handler.handle = AsyncMock(return_value=[FakeChunk(), FakeChunk()])

    tool = RagTool(retrieve_handler=handler, tenant_id="t1")

    # Patch BaseTool.execute to call _execute_impl directly for unit testing
    result = await tool._execute_impl({"query": "lubrication schedule", "top_k": 2})

    handler.handle.assert_awaited_once()
    assert len(result) == 2
    assert result[0]["text"] == FakeChunk.text
    assert result[0]["score"] == FakeChunk.score
    assert result[0]["doc_id"] == FakeChunk.doc_id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_inprocess_passes_filters():
    """Machine IDs and doc_types are forwarded to the handler query."""
    from backend.services.rag_service.src.application.queries.retrieve_context import RetrieveContextQuery

    handler = AsyncMock()
    handler.handle = AsyncMock(return_value=[FakeChunk()])

    tool = RagTool(retrieve_handler=handler, tenant_id="tenant-X")

    await tool._execute_impl({
        "query":       "bearing wear",
        "machine_ids": ["CNC-01", "CNC-02"],
        "doc_types":   ["incident_report"],
        "top_k":       3,
    })

    call_args = handler.handle.call_args[0][0]
    assert isinstance(call_args, RetrieveContextQuery)
    assert call_args.tenant_id == "tenant-X"
    assert call_args.machine_ids == ["CNC-01", "CNC-02"]
    assert call_args.doc_types == ["incident_report"]
    assert call_args.top_k == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_inprocess_raises_on_handler_error():
    """If the handler raises, RagTool propagates the exception."""
    handler = AsyncMock()
    handler.handle = AsyncMock(side_effect=RuntimeError("Qdrant unreachable"))

    tool = RagTool(retrieve_handler=handler, tenant_id="t1")

    with pytest.raises(RuntimeError, match="Qdrant unreachable"):
        await tool._execute_impl({"query": "test query"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_inprocess_ignores_legacy_client():
    """When both retrieve_handler and rag_client are provided, in-process wins."""
    handler    = AsyncMock()
    handler.handle = AsyncMock(return_value=[FakeChunk()])
    legacy_client = AsyncMock()

    tool = RagTool(retrieve_handler=handler, rag_client=legacy_client, tenant_id="t1")
    await tool._execute_impl({"query": "test"})

    handler.handle.assert_awaited_once()
    legacy_client.post.assert_not_called()


# ── Path B: Legacy HTTP fallback ──────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_legacy_http_calls_rag_client():
    """With only rag_client injected, RagTool falls back to the HTTP path."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={
        "chunks": [{"text": "legacy chunk", "score": 0.7, "doc_id": "d-001", "metadata": {}}]
    })

    rag_client = AsyncMock()
    rag_client.post = AsyncMock(return_value=mock_response)

    tool = RagTool(rag_client=rag_client, tenant_id="t1")

    result = await tool._execute_impl({"query": "pump failure modes", "top_k": 1})

    rag_client.post.assert_awaited_once()
    call_args = rag_client.post.call_args
    assert call_args[0][0] == "/api/v1/retrieve"
    assert call_args[1]["json"]["query"] == "pump failure modes"
    assert len(result) == 1
    assert result[0]["text"] == "legacy chunk"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_legacy_http_raises_on_failure():
    """HTTP errors are wrapped in a ValueError."""
    rag_client = AsyncMock()
    rag_client.post = AsyncMock(side_effect=Exception("Connection refused"))

    tool = RagTool(rag_client=rag_client)

    with pytest.raises(ValueError, match="Failed to fetch RAG context"):
        await tool._execute_impl({"query": "bearing temperature spike"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_warns_when_only_legacy_client(caplog):
    """Injecting only rag_client should emit a deprecation warning at construction."""
    import logging
    rag_client = AsyncMock()

    with caplog.at_level(logging.WARNING, logger="backend.services.agent_service.src.infrastructure.tools.rag_tool"):
        tool = RagTool(rag_client=rag_client)

    assert any("deprecated" in r.message.lower() for r in caplog.records), \
        "Expected deprecation warning when injecting only rag_client"


# ── Error cases ───────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_raises_when_no_handler_configured():
    """RagTool with neither retrieve_handler nor rag_client raises RuntimeError."""
    tool = RagTool()  # no args

    with pytest.raises(RuntimeError, match="neither 'retrieve_handler' nor 'rag_client'"):
        await tool._execute_impl({"query": "should fail"})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_raises_when_query_missing():
    """Missing query parameter raises ValueError regardless of handler config."""
    handler = AsyncMock()
    handler.handle = AsyncMock(return_value=[])
    tool = RagTool(retrieve_handler=handler)

    with pytest.raises(ValueError, match="'query' parameter is required"):
        await tool._execute_impl({})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rag_tool_defaults_top_k_to_5():
    """top_k defaults to 5 when not provided."""
    from backend.services.rag_service.src.application.queries.retrieve_context import RetrieveContextQuery

    handler = AsyncMock()
    handler.handle = AsyncMock(return_value=[])
    tool = RagTool(retrieve_handler=handler, tenant_id="t1")

    await tool._execute_impl({"query": "default top_k test"})

    query_arg = handler.handle.call_args[0][0]
    assert query_arg.top_k == 5
