import asyncio
import logging
from typing import List, Tuple

from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """
    Reranker utilizing a local cross-encoder model.
    Default: cross-encoder/ms-marco-MiniLM-L-6-v2 (fast and effective for English).
    Batch reranks (query, passage) pairs and returns top_k results.

    The model is lazy-loaded on first use via ``ensure_loaded()``, which runs the
    synchronous ``CrossEncoder(...)`` constructor in a thread pool so it never
    blocks the asyncio event loop. Cold startup is unaffected.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", batch_size: int = 32):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: CrossEncoder | None = None  # lazy-loaded on first rerank() call

    # ── Lazy loading ──────────────────────────────────────────────────────────

    def _load_model_sync(self) -> None:
        """Synchronous model load — called from a thread pool, never on the event loop."""
        if self._model is None:
            logger.info("Loading CrossEncoder model %s", self.model_name)
            self._model = CrossEncoder(self.model_name)
            logger.info("CrossEncoder model loaded successfully.")

    async def ensure_loaded(self) -> None:
        """Ensure the model is loaded.  Safe to call multiple times (idempotent).

        Runs the blocking CrossEncoder constructor in a thread pool executor so
        it does not stall the asyncio event loop during the first rerank call.
        Subsequent calls return immediately (model already loaded).
        """
        if self._model is None:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._load_model_sync)

    # ── Public API ────────────────────────────────────────────────────────────

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 10,
        min_score: float = 0.1,
    ) -> List[Tuple[int, float]]:
        """
        Rerank a list of documents against a query.

        Args:
            query:     The search query.
            documents: List of document texts to rerank.
            top_k:     Number of top results to return.
            min_score: Minimum score threshold to keep a result.

        Returns:
            List of (original_index, score) tuples, sorted descending by score.
        """
        if not documents:
            return []

        # Ensure model is loaded (non-blocking on event loop)
        await self.ensure_loaded()

        # CrossEncoder expects [[query, doc1], [query, doc2], ...]
        pairs = [[query, doc] for doc in documents]

        # Run inference in thread pool — model.predict() is CPU-bound / blocking
        loop = asyncio.get_running_loop()
        scores = await loop.run_in_executor(
            None,
            lambda: self._model.predict(pairs, batch_size=self.batch_size),
        )

        scored_results = [(idx, float(score)) for idx, score in enumerate(scores)]
        filtered = [r for r in scored_results if r[1] >= min_score]
        filtered.sort(key=lambda x: x[1], reverse=True)
        return filtered[:top_k]
