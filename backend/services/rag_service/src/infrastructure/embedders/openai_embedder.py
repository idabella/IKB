import logging
import os
from typing import List

from openai import AsyncOpenAI, OpenAIError

logger = logging.getLogger(__name__)


class OpenAIEmbedder:
    """
    Production OpenAI Embedder targeting individual string inputs.
    Requires OPENAI_API_KEY to be set in the environment to enforce fail-fast startup.
    """

    def __init__(self) -> None:
        self.model_name = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self.api_key = os.getenv("OPENAI_API_KEY")
        
        if not self.api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY is required and not set. Cannot start rag_service without a valid embedding client."
            )
            
        self.client = AsyncOpenAI(api_key=self.api_key)
        logger.info("Initialized OpenAIEmbedder with model %s", self.model_name)

    async def embed(self, text: str) -> List[float]:
        """
        Embed a single string. 
        Traps OpenAI API errors to log them, then immediately re-raises to prevent empty vector writes.
        """
        try:
            response = await self.client.embeddings.create(
                input=text,
                model=self.model_name
            )
            return response.data[0].embedding
        except OpenAIError as e:
            logger.error("OpenAI embedding API call failed: %s", str(e))
            raise e
