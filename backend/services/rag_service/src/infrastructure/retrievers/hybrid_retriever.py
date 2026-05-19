import os
import logging
from typing import Any, Dict, List

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, MatchAny

logger = logging.getLogger(__name__)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")


class HybridRetriever:
    """
    Production Hybrid Retriever utilizing Qdrant for semantic and filtered search.
    """
    def __init__(self, qdrant_client: AsyncQdrantClient, embedder: Any) -> None:
        self.qdrant = qdrant_client
        self.embedder = embedder
        self.collection_name = "knowledge_chunks"

    async def retrieve(self, query: str, top_k: int = 5, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Retrieves semantic knowledge chunks utilizing Dense Vectors and metadata filtering.
        """
        if filters is None:
            filters = {}

        try:
            # 1. Embed query
            query_vector = await self.embedder.embed(query)

            # 2. Build Qdrant filters
            must_conditions = []

            tenant_id = filters.get("tenant_id")
            if tenant_id:
                must_conditions.append(
                    FieldCondition(
                        key="metadata.tenant_id",
                        match=MatchValue(value=tenant_id)
                    )
                )

            # 3. & 4. Optional Metadata filters
            machine_ids = filters.get("machine_ids")
            if machine_ids and isinstance(machine_ids, list):
                must_conditions.append(
                    FieldCondition(
                        key="metadata.machine_id",
                        match=MatchAny(any=machine_ids)
                    )
                )

            doc_types = filters.get("doc_types")
            if doc_types and isinstance(doc_types, list):
                must_conditions.append(
                    FieldCondition(
                        key="metadata.doc_type",
                        match=MatchAny(any=doc_types)
                    )
                )

            qdrant_filter = Filter(must=must_conditions) if must_conditions else None

            # 5. Execute search against Qdrant
            search_result = await self.qdrant.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=qdrant_filter,
                limit=top_k
            )

            # 6. Map hits
            results = []
            for hit in search_result:
                payload = hit.payload or {}
                results.append({
                    "chunk_id": str(hit.id),
                    "text": payload.get("text", ""),
                    "score": float(hit.score),
                    "metadata": payload.get("metadata", {})
                })

            return results

        except Exception as e:
            logger.error("HybridRetriever failed to retrieve context: %s", str(e))
            return []
