from __future__ import annotations

import asyncio
import json
import logging
import time
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exception
# ---------------------------------------------------------------------------

class CircuitBreakerOpenError(Exception):
    """Raised when a call is attempted while the circuit breaker is OPEN.

    Attributes:
        name:        Human-readable name of the circuit breaker instance.
        retry_after: Approximate seconds remaining before the breaker will
                     transition to HALF_OPEN and allow a trial call.
    """

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = max(0.0, retry_after)
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. "
            f"Retry after {self.retry_after:.1f}s."
        )


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Async-compatible circuit breaker with optional Redis-backed persistence.

    State machine
    -------------
    CLOSED  ─── failure_threshold consecutive failures ──► OPEN
    OPEN    ─── recovery_timeout elapsed ─────────────────► HALF_OPEN
    HALF_OPEN ─ single trial call succeeds ───────────────► CLOSED
    HALF_OPEN ─ trial call fails ─────────────────────────► OPEN  (timer reset)

    Redis persistence
    -----------------
    When ``redis_client`` is supplied the breaker serialises its state to a
    Redis hash (``circuit_breaker:{name}``) on every transition and reads it
    on the first ``call``.  This allows circuit state to survive container
    restarts and to be shared across multiple service replicas.

    If Redis is unavailable the breaker degrades silently to in-memory state
    so it never becomes a hard dependency.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        redis_client: Any | None = None,
        on_open: Callable[[], None] | None = None,
        on_half_open: Callable[[], None] | None = None,
        on_close: Callable[[], None] | None = None,
    ) -> None:
        """
        Args:
            name:               Human-readable identifier used in logs, errors,
                                and the Redis persistence key.
            failure_threshold:  Consecutive failures before the breaker opens.
            recovery_timeout:   Seconds to wait in OPEN before allowing a trial.
            half_open_max_calls: Number of consecutive successes in HALF_OPEN
                                required to close the breaker (default 1 —
                                single trial call).
            redis_client:       Optional async Redis client
                                (e.g. ``redis.asyncio.Redis``).  When supplied,
                                state is persisted across restarts.  The client
                                must expose ``hset``, ``hgetall``, and ``delete``
                                coroutines.
            on_open:            Optional callback fired on CLOSED → OPEN.
            on_half_open:       Optional callback fired on OPEN → HALF_OPEN.
            on_close:           Optional callback fired on HALF_OPEN → CLOSED.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._redis = redis_client
        self._redis_key = f"circuit_breaker:{name}"

        # In-memory state (authoritative when Redis is absent)
        self._state = CircuitState.CLOSED
        self._failure_count: int = 0
        self._half_open_success_count: int = 0
        self._last_failure_time: float | None = None
        self._half_open_in_flight: bool = False  # ONE trial call at a time

        self._lock = asyncio.Lock()

        # Optional transition callbacks
        self.on_open = on_open
        self.on_half_open = on_half_open
        self.on_close = on_close

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Execute a coroutine through the circuit breaker.

        Args:
            coro: The coroutine to execute.

        Returns:
            The return value of ``coro`` on success.

        Raises:
            CircuitBreakerOpenError: If the breaker is OPEN (or HALF_OPEN with
                                     a trial already in flight).
            Exception:               Whatever ``coro`` itself raises.
        """
        async with self._lock:
            # Sync in-memory state from Redis on first use (best-effort).
            await self._load_state_from_redis()
            self._evaluate_timeout()

            if self._state == CircuitState.OPEN:
                elapsed = (
                    time.time() - self._last_failure_time
                    if self._last_failure_time
                    else 0.0
                )
                raise CircuitBreakerOpenError(
                    name=self.name,
                    retry_after=self.recovery_timeout - elapsed,
                )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight:
                    # A trial call is already running; reject subsequent callers
                    # until we know whether the probe succeeded or failed.
                    raise CircuitBreakerOpenError(
                        name=self.name,
                        retry_after=0.0,
                    )
                # Claim the single trial slot.
                self._half_open_in_flight = True

        try:
            result = await coro
            await self._record_success()
            return result
        except Exception as exc:
            await self._record_failure()
            raise

    # ------------------------------------------------------------------
    # State evaluation
    # ------------------------------------------------------------------

    def _evaluate_timeout(self) -> None:
        """Transition OPEN → HALF_OPEN once recovery_timeout has elapsed."""
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_time is not None
            and (time.time() - self._last_failure_time) >= self.recovery_timeout
        ):
            self._transition_to(CircuitState.HALF_OPEN)

    # ------------------------------------------------------------------
    # Success / failure recording
    # ------------------------------------------------------------------

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_in_flight = False
                self._half_open_success_count += 1
                logger.debug(
                    "CircuitBreaker '%s' HALF_OPEN success %d/%d",
                    self.name,
                    self._half_open_success_count,
                    self.half_open_max_calls,
                )
                if self._half_open_success_count >= self.half_open_max_calls:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                # Reset rolling failure counter on any success.
                self._failure_count = 0

            await self._persist_state_to_redis()

    async def _record_failure(self) -> None:
        async with self._lock:
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure during the trial call reopens the breaker and
                # resets the recovery timer so we wait a full timeout again.
                self._half_open_in_flight = False
                logger.warning(
                    "CircuitBreaker '%s' trial call failed — reopening.",
                    self.name,
                )
                self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                logger.debug(
                    "CircuitBreaker '%s' failure %d/%d",
                    self.name,
                    self._failure_count,
                    self.failure_threshold,
                )
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)

            await self._persist_state_to_redis()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state

        logger.info(
            "CircuitBreaker '%s' transitioned %s → %s",
            self.name,
            old_state.name,
            new_state.name,
        )

        if new_state == CircuitState.OPEN:
            if self.on_open:
                self.on_open()

        elif new_state == CircuitState.HALF_OPEN:
            # Reset probe counters whenever we enter HALF_OPEN.
            self._half_open_success_count = 0
            self._half_open_in_flight = False
            if self.on_half_open:
                self.on_half_open()

        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_success_count = 0
            self._half_open_in_flight = False
            if self.on_close:
                self.on_close()

    # ------------------------------------------------------------------
    # Redis persistence (optional, best-effort)
    # ------------------------------------------------------------------

    async def _persist_state_to_redis(self) -> None:
        """Serialise current state to Redis.  Silently no-ops if Redis is absent
        or unavailable — in-memory state remains authoritative."""
        if self._redis is None:
            return

        payload = {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "half_open_success_count": self._half_open_success_count,
            "last_failure_time": self._last_failure_time or "",
        }

        try:
            await self._redis.hset(self._redis_key, mapping=payload)
            logger.debug(
                "CircuitBreaker '%s' state persisted to Redis: %s",
                self.name,
                self._state.value,
            )
        except Exception:
            logger.warning(
                "CircuitBreaker '%s' failed to persist state to Redis — "
                "continuing with in-memory state.",
                self.name,
                exc_info=True,
            )

    async def _load_state_from_redis(self) -> None:
        """Hydrate in-memory state from Redis on the first call after startup.
        Silently no-ops if Redis is absent or the key does not exist."""
        if self._redis is None:
            return

        try:
            raw: dict[bytes | str, bytes | str] = await self._redis.hgetall(
                self._redis_key
            )
            if not raw:
                return

            # Normalise keys/values to str regardless of Redis client flavour.
            data: dict[str, str] = {
                (k.decode() if isinstance(k, bytes) else k): (
                    v.decode() if isinstance(v, bytes) else v
                )
                for k, v in raw.items()
            }

            self._state = CircuitState(data.get("state", CircuitState.CLOSED.value))
            self._failure_count = int(data.get("failure_count", 0))
            self._half_open_success_count = int(
                data.get("half_open_success_count", 0)
            )
            raw_lft = data.get("last_failure_time", "")
            self._last_failure_time = float(raw_lft) if raw_lft else None

            logger.info(
                "CircuitBreaker '%s' state restored from Redis: %s",
                self.name,
                self._state.value,
            )

            # After loading, disable future loads so we don't overwrite live
            # in-memory state with stale Redis data on subsequent calls.
            self._redis = None  # type: ignore[assignment]

        except Exception:
            logger.warning(
                "CircuitBreaker '%s' failed to load state from Redis — "
                "starting with default CLOSED state.",
                self.name,
                exc_info=True,
            )