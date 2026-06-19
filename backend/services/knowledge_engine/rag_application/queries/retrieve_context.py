from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from prometheus_client import Counter, Histogram
from pydantic import BaseModel, ConfigDict

from backend.services.knowledge_engine.rag.rerankers.cross_encoder_reranker import CrossEncoderReranker
from backend.services.knowledge_engine.rag.retrievers.multi_query_retriever import MultiQueryRetriever
from backend.services.knowledge_engine.rag.retrievers.parent_retriever import ParentRetriever

logger = logging.getLogger(__name__)

# Prometheus Metrics
RETRIEVAL_LATENCY = Histogram(
    "retrieval_latency_ms",
    "Latency of the full retrieval pipeline in milliseconds",
)
RERANK_LATENCY = Histogram(
    "rerank_latency_ms",
    "Latency of the reranking step in milliseconds",
)
EMPTY_RESULT_COUNT = Counter(
    "empty_result_count",
    "Number of queries that returned zero results",
)


class RetrieveContextQuery(BaseModel):
    """Query object for context retrieval.

    machine_ids filter behaviour
    ----------------------------
    - ``None`` or ``[]``        → no machine filter applied (all machines in tenant)
    - ``["machine-01"]``        → exact match on a single machine
    - ``["machine-01", "machine-02"]`` → MatchAny across the listed machines

    Examples (doctest stubs — run against a wired handler in integration tests):

    # Single machine_id → filters["machine_id"] = "machine-01"
    >>> q = RetrieveContextQuery(query="vibration spike", tenant_id="t1", machine_ids=["machine-01"])
    >>> q.machine_ids
    ['machine-01']

    # Multi machine_ids → filters["machine_ids"] = ["machine-01", "machine-02"]
    >>> q = RetrieveContextQuery(query="vibration spike", tenant_id="t1", machine_ids=["machine-01", "machine-02"])
    >>> len(q.machine_ids)
    2

    # Empty list → no filter key injected
    >>> q = RetrieveContextQuery(query="vibration spike", tenant_id="t1", machine_ids=[])
    >>> bool(q.machine_ids)
    False
    """

    model_config = ConfigDict(frozen=True)

    query: str
    tenant_id: str
    machine_ids: Optional[List[str]] = None
    doc_types: Optional[List[str]] = None
    top_k: int = 20
    rerank: bool = True
    use_multi_query: bool = False  # opt-in: generates N query variants via LLM (adds 2-3 LLM calls)
    filters: Dict[str, Any] = {}


@dataclass
class RetrievalResult:
    chunk_id: str
    text: str
    score: float
    metadata: Dict[str, Any]
    source_doc: str


class RetrieveContextHandler:
    """
    CQRS Handler orchestrating the complete RAG retrieval pipeline:
    1. Multi-Query Expansion & Hybrid Retrieval (BM25 + Dense Qdrant + RRF)
    2. Parent Context Expansion (Redis)
    3. Cross-Encoder Reranking
    4. Formatting & Metrics Logging

    Hard latency budget: < 500ms p95.
    """

    def __init__(
        self,
        multi_query_retriever: MultiQueryRetriever,
        parent_retriever: ParentRetriever,
        reranker: CrossEncoderReranker,
    ) -> None:
        self.multi_query_retriever = multi_query_retriever
        self.parent_retriever = parent_retriever
        self.reranker = reranker

    async def handle(self, query: RetrieveContextQuery) -> List[RetrievalResult]:
        start_time = time.time()

        # ── Build strict filters ──────────────────────────────────────────────
        filters: Dict[str, Any] = query.filters.copy()

        if query.machine_ids:
            if len(query.machine_ids) == 1:
                # Single machine → scalar MatchValue in Qdrant
                filters["machine_id"] = query.machine_ids[0]
                logger.debug(
                    "Machine filter applied: machine_id=%s",
                    query.machine_ids[0],
                )
            else:
                # Multiple machines → MatchAny in Qdrant; never silently drop.
                filters["machine_ids"] = query.machine_ids
                logger.debug(
                    "Machine filter applied: machine_ids=%s (%d machines)",
                    query.machine_ids,
                    len(query.machine_ids),
                )
        if query.doc_types:
            filters["doc_types"] = query.doc_types
        elif not query.machine_ids:
            logger.debug(
                "No machine_id filter requested — returning results across all "
                "machines for tenant_id=%s",
                query.tenant_id,
            )

        # ── 1. Retrieval ──────────────────────────────────────────────────────
        if query.use_multi_query:
            # Multi-Query: generates N variants via LLM, deduplicates results.
            # Improves recall for ambiguous queries at the cost of 2-3 LLM API calls.
            retrieved_points = await self.multi_query_retriever.retrieve(
                tenant_id=query.tenant_id,
                query=query.query,
                filters=filters,
                top_k=query.top_k * 2 if query.rerank else query.top_k,
            )
        else:
            # Direct hybrid retrieval (default) — single embedding call, no LLM.
            retrieved_points = await self.multi_query_retriever.hybrid_retriever.search(
                tenant_id=query.tenant_id,
                query_vector=await self.multi_query_retriever.hybrid_retriever.embedder.embed(query.query),
                filters=filters,
                limit=query.top_k * 2 if query.rerank else query.top_k,
            )

        if not retrieved_points:
            EMPTY_RESULT_COUNT.inc()
            logger.warning("No results found for query: '%s'", query.query)
            return []

        # ── 2. Parent Expansion ───────────────────────────────────────────────
        expanded_points = await self.parent_retriever.expand_to_parents(retrieved_points)

        final_results: List[RetrievalResult] = []

        # ── 3. Reranking ──────────────────────────────────────────────────────
        if query.rerank:
            rerank_start = time.time()
            documents = [p.payload.get("text", "") for p in expanded_points]

            reranked_tuples = await self.reranker.rerank(
                query=query.query,
                documents=documents,
                top_k=query.top_k,
                min_score=0.1,
            )

            RERANK_LATENCY.observe((time.time() - rerank_start) * 1000)

            for idx, score in reranked_tuples:
                point = expanded_points[idx]
                final_results.append(
                    RetrievalResult(
                        chunk_id=point.id,
                        text=point.payload.get("text", ""),
                        score=score,
                        metadata=point.payload,
                        source_doc=point.payload.get("doc_id", "unknown"),
                    )
                )
        else:
            for point in expanded_points[: query.top_k]:
                final_results.append(
                    RetrievalResult(
                        chunk_id=point.id,
                        text=point.payload.get("text", ""),
                        score=point.score,
                        metadata=point.payload,
                        source_doc=point.payload.get("doc_id", "unknown"),
                    )
                )

        # ── 4. Latency Budget ─────────────────────────────────────────────────
        total_latency = (time.time() - start_time) * 1000
        RETRIEVAL_LATENCY.observe(total_latency)

        if total_latency > 500:
            logger.warning(
                "Latency budget exceeded! Total time: %.2f ms", total_latency
            )
        else:
            logger.info("Retrieval completed in %.2f ms", total_latency)

        return final_results