from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List

from backend.services.rag_service.src.infrastructure.retrievers.hybrid_retriever import HybridRetriever

if TYPE_CHECKING:
    from backend.services.agent_service.src.infrastructure.llm_clients.base_llm_client import BaseLLMClient

logger = logging.getLogger(__name__)


class MultiQueryRetriever:
    """
    Multi-Query Expansion Retriever.

    Takes an original query, generates N=3 alternative phrasings via an LLM,
    and runs the HybridRetriever for each phrasing in parallel.
    Deduplicates results by chunk_id and boosts scores based on frequency
    of appearance across phrasings.

    Args:
        hybrid_retriever: Configured HybridRetriever instance.
        llm_client:       Required LLM client used for query expansion.
                          Must implement BaseLLMClient (e.g. AnthropicClient).
                          Passing None raises ValueError at construction time —
                          silent fallback to single-query mode is intentionally
                          not supported.

    Raises:
        ValueError: If llm_client is None.
    """

    def __init__(
        self,
        hybrid_retriever: HybridRetriever,
        llm_client: "BaseLLMClient",
    ) -> None:
        if llm_client is None:
            logger.critical(
                "MultiQueryRetriever requires a configured llm_client. "
                "Query expansion is unavailable — startup aborted to prevent "
                "silent single-query degradation."
            )
            raise ValueError(
                "MultiQueryRetriever requires an llm_client. "
                "Provide an AnthropicClient or compatible BaseLLMClient."
            )

        self.hybrid_retriever = hybrid_retriever
        self.llm_client: BaseLLMClient = llm_client

    async def _generate_queries(self, original_query: str) -> List[str]:
        """Generate 3 alternative phrasings via LLM to improve recall.

        llm_client availability is guaranteed by __init__ invariant;
        no None-check is performed here.
        """
        prompt = (
            f"You are an industrial AI assistant. Generate exactly 3 alternative phrasings "
            f"of the following query to improve document retrieval recall. Each on a new line. "
            f"No numbering, no bullet points. Query: {original_query}"
        )

        try:
            response = await self.llm_client.complete(prompt)
            queries = [line.strip() for line in response.split("\n") if line.strip()]

            if not queries:
                return [original_query]

            return queries

        except Exception as e:
            logger.warning(
                "LLM query generation failed, falling back to original query: %s",
                str(e),
            )
            return [original_query]

    async def retrieve(
        self,
        tenant_id: str,
        query: str,
        filters: Dict[str, Any],
        top_k: int = 20,
    ) -> List[Dict[str, Any]]:
        """Execute multi-query expansion and retrieval."""
        if filters is None:
            filters = {}
        filters["tenant_id"] = tenant_id

        phrasings = await self._generate_queries(query)
        logger.info("Generated %d phrasings for query: '%s'", len(phrasings), query)

        tasks = [
            self.hybrid_retriever.retrieve(query=phrasing, top_k=top_k, filters=filters)
            for phrasing in phrasings
        ]

        results_list = await asyncio.gather(*tasks)

        unique_results: Dict[str, Dict[str, Any]] = {}
        frequencies: Dict[str, int] = {}

        for results in results_list:
            for res in results:
                chunk_id = res["chunk_id"]
                score = res["score"]
                frequencies[chunk_id] = frequencies.get(chunk_id, 0) + 1

                if chunk_id not in unique_results or score > unique_results[chunk_id]["score"]:
                    unique_results[chunk_id] = res

        final_list = []
        for chunk_id, res in unique_results.items():
            freq = frequencies[chunk_id]
            boosted_score = res["score"] + (freq * 0.1)

            boosted_res = res.copy()
            boosted_res["score"] = boosted_score
            final_list.append(boosted_res)

        final_list.sort(key=lambda x: x["score"], reverse=True)
        return final_list[:top_k]