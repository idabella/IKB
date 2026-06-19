import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level fallback — subclasses override via their own class attribute.
# Keeping it here (rather than inline in __init__) makes it grep-able and
# patchable in tests without touching any class definition.
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT: float = 30.0


class ToolResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    success: bool
    data: Any
    error: Optional[str] = None
    latency_ms: float = 0.0

    # ------------------------------------------------------------------
    # Named constructors requested by the task spec.
    # `model_config = frozen=True` means we must go through __init__;
    # classmethods are the clean way to offer ergonomic call-sites while
    # keeping the model immutable.
    # ------------------------------------------------------------------
    @classmethod
    def ok(cls, data: Any, latency_ms: float = 0.0) -> "ToolResult":
        """Return a successful result carrying `data`."""
        return cls(success=True, data=data, latency_ms=latency_ms)

    @classmethod
    def fail(cls, message: str, latency_ms: float = 0.0) -> "ToolResult":
        """Return a failed result carrying an error `message`."""
        return cls(success=False, data=None, error=message, latency_ms=latency_ms)


class BaseTool(ABC):
    """Abstract base class for all Agent Tools.

    Subclasses must:
    - Set class-level ``name``, ``description``, and ``input_schema``.
    - Override ``_execute_impl`` with their domain logic.
    - Optionally set ``timeout_seconds`` to control per-tool deadline.

    The public entry point is ``execute``; it owns latency tracking,
    timeout enforcement, and error normalisation so subclasses never have
    to repeat that boilerplate.
    """

    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema dict passed to the LLM tool spec

    # Per-subclass override; falls back to the module constant if not set.
    timeout_seconds: float = DEFAULT_TIMEOUT

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """Execute the tool with deadline enforcement and structured error handling.

        Control flow
        ────────────
                             execute(params)
                                   │
                      ┌────────────▼─────────────┐
                      │  asyncio.wait_for(        │
                      │    _execute_impl(params), │
                      │    timeout=timeout_seconds│
                      │  )                        │
                      └──────┬──────────┬─────────┘
                             │          │
                    success  │          │  exception
                             ▼          ▼
                       ToolResult   ┌───┴──────────────┐
                          .ok()     │ TimeoutError      │ other Exception
                                    │ → log ERROR       │ → log ERROR
                                    │ → .fail(timeout)  │ → .fail(str(e))
                                    └───────────────────┘

        Both failure branches record wall-clock latency so callers can
        distinguish "slow-then-failed" from "fast-then-failed" in metrics.
        """
        tool_name: str = self.__class__.__name__
        start_time: float = time.perf_counter()   # perf_counter > time.time() for short intervals

        try:
            data: Any = await asyncio.wait_for(
                self._execute_impl(params),
                timeout=self.timeout_seconds,
            )
            latency_ms: float = (time.perf_counter() - start_time) * 1_000
            return ToolResult.ok(data=data, latency_ms=latency_ms)

        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1_000
            logger.error(
                "Tool %s timed out after %.1fs",
                tool_name,
                self.timeout_seconds,
            )
            return ToolResult.fail(
                message=f"Tool execution timed out after {self.timeout_seconds}s",
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1_000
            logger.error(
                "Tool %s raised an unexpected error: %s",
                tool_name,
                exc,
                exc_info=True,    # attaches full traceback to the log record
            )
            return ToolResult.fail(
                message=str(exc),
                latency_ms=latency_ms,
            )

    @abstractmethod
    async def _execute_impl(self, params: Dict[str, Any]) -> Any:
        """Domain logic — override in every concrete tool.

        Raise any exception freely; ``execute`` will catch, log, and
        normalise it into a ``ToolResult``.  Do NOT catch ``asyncio.TimeoutError``
        here — let it propagate so the deadline in ``execute`` is honoured.
        """