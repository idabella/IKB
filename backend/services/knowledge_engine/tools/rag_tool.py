from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.services.knowledge_engine.tools.base_tool import BaseTool

logger = logging.getLogger(__name__)


class RagTool(BaseTool):
    """
    Tool to perform semantic retrieval from industrial knowledge documents.

    ARCHITECTURE CHANGE (Consolidated Knowledge Engine):
    Previously this tool held an `httpx.AsyncClient` pointed at the standalone
    rag_service and made a network call:
        POST http://rag-service:8000/api/v1/retrieve

    Now the tool calls the RetrieveContextHandler *in-process*, eliminating
    the serialization/deserialization overhead and the full TCP round-trip
    that represented the primary bottleneck inside the ReAct agent loop.
    """

    name = "rag_search"
    description = (
        "Search maintenance manuals, incident reports, and technical documents "
        "for semantic information relevant to industrial diagnostics."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The diagnostic or troubleshooting search query.",
            },
            "machine_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of machine IDs to filter results by.",
            },
            "doc_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional document type filter (e.g. 'manual', 'incident_report').",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of chunk results to return.",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(
        self,
        retrieve_handler: Any = None,
        # Legacy parameter kept for backwards compatibility during migration;
        # rag_client is ignored when retrieve_handler is provided.
        rag_client: Any = None,
        tenant_id: str = "default",
    ) -> None:
        self._retrieve_handler = retrieve_handler
        self._tenant_id = tenant_id
        # Warn if someone still injects the old HTTP client
        if rag_client is not None and retrieve_handler is None:
            logger.warning(
                "RagTool: 'rag_client' (HTTP) is deprecated. "
                "Inject 'retrieve_handler' (RetrieveContextHandler) instead "
                "for in-process retrieval without network overhead."
            )
            self._rag_client_legacy = rag_client
        else:
            self._rag_client_legacy = None

    async def _execute_impl(self, params: Dict[str, Any]) -> Any:
        query: Optional[str] = params.get("query")
        if not query:
            raise ValueError("RagTool: 'query' parameter is required.")

        top_k: int = int(params.get("top_k", 5))
        machine_ids: List[str] = params.get("machine_ids") or []
        doc_types: List[str] = params.get("doc_types") or []

        # ── Path A: In-process call (preferred, no network hop) ─────────────
        if self._retrieve_handler is not None:
            from backend.services.knowledge_engine.rag_application.queries.retrieve_context import (
                RetrieveContextQuery,
            )

            context_query = RetrieveContextQuery(
                query=query,
                tenant_id=self._tenant_id,
                machine_ids=machine_ids,
                doc_types=doc_types,
                top_k=top_k,
            )
            logger.info("RagTool: in-process retrieval for query='%.60s'", query)
            results = await self._retrieve_handler.handle(context_query)
            return [
                {"text": r.text, "score": r.score, "doc_id": r.doc_id, "metadata": r.metadata}
                for r in results
            ]

        # ── Path B: Legacy HTTP fallback (deprecated, kept for migration) ───
        if self._rag_client_legacy is not None:
            logger.warning(
                "RagTool: falling back to deprecated HTTP client for query='%.60s'. "
                "Migrate to in-process RetrieveContextHandler.",
                query,
            )
            body = {
                "query": query,
                "top_k": top_k,
                "filters": {"machine_ids": machine_ids, "doc_types": doc_types},
            }
            try:
                response = await self._rag_client_legacy.post("/api/v1/retrieve", json=body)
                response.raise_for_status()
                data = response.json()
                return data.get("chunks", [])
            except Exception as exc:
                logger.error("RagTool HTTP fallback failed: %s", exc)
                raise ValueError(f"Failed to fetch RAG context: {exc}")

        raise RuntimeError(
            "RagTool: neither 'retrieve_handler' nor 'rag_client' is configured. "
            "Inject a RetrieveContextHandler for in-process retrieval."
        )
