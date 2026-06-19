from __future__ import annotations

import logging
from typing import Any, Dict, List

from qdrant_client.http.models import Filter, FieldCondition, MatchValue, MatchAny

from backend.services.knowledge_engine.rag.vector_stores.qdrant_store import QdrantStore, ScoredPoint

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    Hybrid Retriever built on QdrantStore.

    Provides two call paths used by the retrieval pipeline:
      - retrieve(query, top_k, filters): used by MultiQueryRetriever (query string → embed → search)
      - search(tenant_id, query_vector, filters, limit): used by RetrieveContextHandler
        non-multi-query path (pre-computed vector)

    Both paths ultimately delegate to QdrantStore.search().
    """

    def __init__(self, vector_store: QdrantStore, embedder: Any) -> None:
        self.vector_store = vector_store
        self.embedder = embedder

    # ── Path 1: used by MultiQueryRetriever ──────────────────────────────────

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Embed `query` then search Qdrant.  Returns a plain list of dicts
        (chunk_id, text, score, metadata) for MultiQueryRetriever's dedup logic.
        """
        if filters is None:
            filters = {}

        tenant_id = filters.get("tenant_id", "default")
        query_vector = await self.embedder.embed(query)

        scored_points = await self.vector_store.search(
            tenant_id=tenant_id,
            query_vector=query_vector,
            filters={k: v for k, v in filters.items() if k != "tenant_id"},
            limit=top_k,
        )

        return [
            {
                "chunk_id": str(p.id),
                "text": p.payload.get("text", ""),
                "score": float(p.score),
                "metadata": p.payload,
            }
            for p in scored_points
        ]

    # ── Path 2: used by RetrieveContextHandler (non-multi-query) ─────────────

    async def search(
        self,
        tenant_id: str,
        query_vector: List[float],
        filters: Dict[str, Any],
        limit: int,
    ) -> List[ScoredPoint]:
        """
        Search with a pre-computed vector.  Returns ScoredPoint objects so
        RetrieveContextHandler can access .id / .score / .payload directly.
        """
        return await self.vector_store.search(
            tenant_id=tenant_id,
            query_vector=query_vector,
            filters=filters,
            limit=limit,
        )
