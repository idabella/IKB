from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional

from google import genai
from google.genai import types

from backend.shared.utils.retry import retry

logger = logging.getLogger(__name__)

# ── Default model ─────────────────────────────────────────────────────────────
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


# ── Normalised response objects (mirrors Anthropic's shape) ───────────────────
# base_agent.py iterates response.content and checks block.type / block.text /
# block.name / block.input / block.id / block.model_dump().
# We produce the same interface so base_agent.py requires minimal changes.

@dataclass
class UsageInfo:
    """Token-usage compatible with the Anthropic UsageInfo interface."""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class NormalizedBlock:
    """
    A single content block — either a text turn or a tool-call request.
    Mirrors the Anthropic content-block interface so base_agent.py works
    without modification.
    """
    type: str           # "text" | "tool_use"
    text: str = ""      # populated for type == "text"
    name: str = ""      # populated for type == "tool_use"
    id: str = ""        # populated for type == "tool_use"
    input: dict = field(default_factory=dict)  # populated for type == "tool_use"

    def model_dump(self) -> Dict[str, Any]:
        """Serialise to the dict shape that base_agent.py appends to messages."""
        if self.type == "text":
            return {"type": "text", "text": self.text}
        return {
            "type": "tool_use",
            "name": self.name,
            "id": self.id,
            "input": self.input,
        }


@dataclass
class NormalizedResponse:
    """
    Wrapper around a Gemini response that looks like an Anthropic Message,
    so base_agent.py can iterate `.content` and access `.usage.*_tokens`.
    """
    content: List[NormalizedBlock]
    usage: UsageInfo


# ── Domain exception ──────────────────────────────────────────────────────────

class LLMClientError(Exception):
    """Domain-level exception for LLM API failures."""
    pass


# ── Main client ───────────────────────────────────────────────────────────────

class GeminiClient:
    """
    Google Gemini async client wrapper for IKB v2.3.

    Drop-in replacement for AnthropicClient:
      - Same ``complete()`` signature
      - Same ``NormalizedResponse`` return shape (base_agent.py unchanged)
      - Same ``stream()`` async-generator contract
      - Tool schemas auto-converted to Gemini FunctionDeclaration format

    Model: ``gemini-2.5-flash`` (override via GEMINI_MODEL env var)
    Auth:  ``GEMINI_API_KEY`` environment variable
    """

    def __init__(self, api_key: str = "", model_name: str = DEFAULT_MODEL) -> None:
        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not resolved_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is required and not set. "
                "Cannot start knowledge_engine without a valid LLM client."
            )
        self.model_name = model_name
        self.client = genai.Client(api_key=resolved_key)

    # ── Tool schema translation ───────────────────────────────────────────────

    @staticmethod
    def _format_tools(tools: List[Any]) -> Optional[List[types.Tool]]:
        """
        Convert BaseTool instances into Gemini ``Tool`` / ``FunctionDeclaration`` format.

        BaseTool exposes:
          .name         → function name
          .description  → function description
          .input_schema → JSON Schema dict (same structure Gemini accepts as ``parameters``)
        """
        if not tools:
            return None
        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_schema,
            )
            for tool in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    # ── Message format translation ────────────────────────────────────────────

    @staticmethod
    def _to_gemini_contents(
        messages: List[Dict[str, Any]],
    ) -> List[types.Content]:
        """
        Convert the shared conversation format (list of role/content dicts) to
        Gemini ``Content`` objects.

        Supported input shapes:
          - ``{"role": "user",      "content": "string"}``
          - ``{"role": "assistant", "content": [{"type": "text", "text": "..."}]}``
          - ``{"role": "user",      "content": [{"type": "tool_result", ...}]}``
          - ``{"role": "assistant", "content": [{"type": "tool_use", ...}]}``

        Notes:
          - Gemini roles are "user" and "model" (not "assistant").
          - Tool results go into a Part with ``function_response``.
          - Tool calls (from assistant) go into a Part with ``function_call``.
        """
        contents: List[types.Content] = []

        for msg in messages:
            role_raw: str = msg.get("role", "user")
            role: str = "model" if role_raw == "assistant" else "user"
            raw_content = msg.get("content", "")

            parts: List[types.Part] = []

            if isinstance(raw_content, str):
                parts.append(types.Part(text=raw_content))

            elif isinstance(raw_content, list):
                for block in raw_content:
                    btype = block.get("type", "")

                    if btype == "text":
                        if block.get("text"):
                            parts.append(types.Part(text=block["text"]))

                    elif btype == "tool_use":
                        # Assistant decided to call a function
                        parts.append(
                            types.Part(
                                function_call=types.FunctionCall(
                                    name=block["name"],
                                    args=block.get("input", {}),
                                )
                            )
                        )

                    elif btype == "tool_result":
                        # User returns the function result
                        content_val = block.get("content", "")
                        is_error = block.get("is_error", False)
                        # Wrap as a function_response Part
                        parts.append(
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=block.get("name", "tool"),
                                    response={
                                        "result": content_val,
                                        "is_error": is_error,
                                    },
                                )
                            )
                        )

            if parts:
                contents.append(types.Content(role=role, parts=parts))

        return contents

    # ── Response normalisation ────────────────────────────────────────────────

    @staticmethod
    def _normalize_response(response: Any) -> NormalizedResponse:
        """
        Convert a Gemini ``GenerateContentResponse`` to ``NormalizedResponse``
        so that base_agent.py can iterate ``.content`` unchanged.
        """
        blocks: List[NormalizedBlock] = []

        candidate = None
        if response.candidates:
            candidate = response.candidates[0]

        if candidate and candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.function_call:
                    # Tool-call request from the model
                    fc = part.function_call
                    args = dict(fc.args) if fc.args else {}
                    blocks.append(
                        NormalizedBlock(
                            type="tool_use",
                            name=fc.name,
                            id=str(uuid.uuid4()),  # Gemini has no call ID; generate one
                            input=args,
                        )
                    )
                elif part.text:
                    blocks.append(NormalizedBlock(type="text", text=part.text))

        # Token usage
        usage = UsageInfo()
        if response.usage_metadata:
            usage.input_tokens  = response.usage_metadata.prompt_token_count or 0
            usage.output_tokens = response.usage_metadata.candidates_token_count or 0

        return NormalizedResponse(content=blocks, usage=usage)

    # ── Public API ────────────────────────────────────────────────────────────

    @retry(max_attempts=3, exceptions=(Exception,), backoff_factor=2.0)
    async def complete(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str = "",
        tools: List[Any] = None,
        stream: bool = False,
        max_tokens: int = 2000,
    ) -> NormalizedResponse:
        """
        Execute a Gemini completion and return a ``NormalizedResponse``.

        Args:
            messages:      Conversation history in role/content dict format.
            system_prompt: System-level instruction for the model.
            tools:         List of BaseTool instances (auto-converted).
            stream:        Unused — streaming is handled by ``.stream()``.
            max_tokens:    Max output tokens.

        Returns:
            ``NormalizedResponse`` whose ``.content`` and ``.usage`` match the
            Anthropic interface expected by ``base_agent.py``.
        """
        contents = self._to_gemini_contents(messages)
        gemini_tools = self._format_tools(tools or [])

        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            max_output_tokens=max_tokens,
            tools=gemini_tools,
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
            return self._normalize_response(response)

        except Exception as exc:
            logger.error("Gemini API call failed: %s", str(exc))
            raise LLMClientError(f"Failed to fetch LLM completion: {exc}") from exc

    async def stream(
        self,
        system_prompt: str,
        query: str,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """
        Stream individual text tokens from Gemini.

        Yields:
            Text fragments as they arrive.  Trailing newline appended by caller.

        Raises:
            ``LLMClientError`` on API failure (yielded inline as ``[ERROR]: ...``).
        """
        config = types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            max_output_tokens=max_tokens,
        )
        contents = [types.Content(role="user", parts=[types.Part(text=query)])]

        try:
            async for chunk in await self.client.aio.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as exc:
            logger.error("Gemini stream error: %s", str(exc), exc_info=True)
            raise LLMClientError(str(exc)) from exc
