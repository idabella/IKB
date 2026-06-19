from __future__ import annotations

import logging
import os
from typing import List, Optional

from google import genai
from google.genai import types

from backend.shared.utils.retry import retry

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
DEFAULT_EMBEDDING_DIM = int(os.getenv("GEMINI_EMBEDDING_DIM", "768"))


class GeminiEmbedder:
    """
    Gemini embedding client for the RAG pipeline.

    Uses ``gemini-embedding-001`` by default with optional output dimensionality
    truncation for efficient Qdrant storage.
    """

    def __init__(
        self,
        api_key: str = "",
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        output_dimensionality: Optional[int] = DEFAULT_EMBEDDING_DIM,
    ) -> None:
        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not resolved_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is required and not set. "
                "Cannot start knowledge_engine without a valid embedding client."
            )

        self.model_name = model_name
        self.output_dimensionality = output_dimensionality
        self.client = genai.Client(api_key=resolved_key)
        logger.info(
            "Initialized GeminiEmbedder model=%s dim=%s",
            self.model_name,
            self.output_dimensionality,
        )

    def _build_config(self, task_type: str) -> types.EmbedContentConfig:
        config_kwargs = {"task_type": task_type}
        if self.output_dimensionality:
            config_kwargs["output_dimensionality"] = self.output_dimensionality
        return types.EmbedContentConfig(**config_kwargs)

    @retry(max_attempts=3, exceptions=(Exception,), backoff_factor=2.0)
    async def embed(self, text: str, task_type: str = "RETRIEVAL_QUERY") -> List[float]:
        """Embed a single string. Defaults to RETRIEVAL_QUERY for search queries."""
        try:
            response = await self.client.aio.models.embed_content(
                model=self.model_name,
                contents=text,
                config=self._build_config(task_type),
            )
            if not response.embeddings:
                raise RuntimeError("Gemini embedding API returned no vectors")
            return list(response.embeddings[0].values)
        except Exception as exc:
            logger.error("Gemini embedding API call failed: %s", exc)
            raise

    async def embed_document(self, text: str) -> List[float]:
        """Embed document text for ingestion (RETRIEVAL_DOCUMENT task type)."""
        return await self.embed(text, task_type="RETRIEVAL_DOCUMENT")
