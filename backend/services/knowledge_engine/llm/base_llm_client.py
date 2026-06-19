from __future__ import annotations

from typing import Any, Dict, List, Protocol

from backend.services.knowledge_engine.llm.gemini_client import NormalizedResponse


class BaseLLMClient(Protocol):
    async def complete(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        tools: List[Any] = None,
        stream: bool = False,
        max_tokens: int = 2000,
    ) -> NormalizedResponse:
        ...
