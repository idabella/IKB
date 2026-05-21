import json
import logging
import uuid
from typing import Dict, List, Optional, Type

import asyncpg

from backend.shared.base.event import DomainEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event Registry
#
# Maps event_type strings (as stored in the DB) to their concrete DomainEvent
# subclasses. Populated at import time via @register_event decorators on each
# concrete class — so registration is co-located with the class definition,
# not in a central switch or config file.
#
# EXTENDING: every new event class must carry the decorator:
#
#   @register_event("MachineFaultDetected")
#   class MachineFaultDetectedEvent(DomainEvent):
#       ...
#
# Registration happens when the module is first imported.  Make sure all
# concrete event modules are imported before the EventStore handles any
# records — the application bootstrap (e.g. `app/main.py`) is the right
# place to do that:
#
#   import backend.domain.events  # noqa: F401  — triggers registration
#
# ---------------------------------------------------------------------------
_EVENT_REGISTRY: Dict[str, Type[DomainEvent]] = {}


def register_event(event_type: str):
    """Class decorator that self-registers a concrete DomainEvent subclass.

    Usage
    -----
    ::

        @register_event("MachineFaultDetected")
        class MachineFaultDetectedEvent(DomainEvent):
            machine_id: str
            fault_code: str

    The string passed to the decorator must match the value stored in the
    ``event_type`` column of the ``events`` table exactly (case-sensitive).

    Raises
    ------
    TypeError
        If the decorated class is not a subclass of ``DomainEvent``.
    ValueError
        If the ``event_type`` key is already registered (prevents silent
        overwrites when two classes accidentally claim the same name).
    """

    def decorator(cls: Type[DomainEvent]) -> Type[DomainEvent]:
        if not (isinstance(cls, type) and issubclass(cls, DomainEvent)):
            raise TypeError(
                f"@register_event can only decorate DomainEvent subclasses, "
                f"got {cls!r}"
            )
        if event_type in _EVENT_REGISTRY:
            existing = _EVENT_REGISTRY[event_type]
            raise ValueError(
                f"Event type '{event_type}' is already registered to "
                f"{existing.__qualname__}. Cannot re-register as {cls.__qualname__}."
            )
        _EVENT_REGISTRY[event_type] = cls
        logger.debug("Registered event type '%s' → %s", event_type, cls.__qualname__)
        return cls

    return decorator


def get_event_registry() -> Dict[str, Type[DomainEvent]]:
    """Return a read-only view of the current event registry.

    Callers should not mutate the returned dict; use ``@register_event``
    for all additions so guard-rails (duplicate checks, type checks) apply.
    """
    # Return a shallow copy so external callers can't corrupt module state.
    return dict(_EVENT_REGISTRY)


class EventStore:
    """Append-only PostgreSQL event store using asyncpg.

    Persists DomainEvents and retrieves aggregate histories.

    Notes
    -----
    ``_row_to_event`` performs a registry lookup for each row rather than
    instantiating ``DomainEvent`` directly (which is abstract).  Rows whose
    ``event_type`` has no registered class are skipped with a warning — this
    makes the store forward-compatible: new event types written by a newer
    service version don't crash older readers.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def append(self, events: List[DomainEvent]) -> None:
        """Append a batch of domain events atomically.

        Args:
            events: The events to persist. A no-op when the list is empty.
        """
        if not events:
            return

        query = """
            INSERT INTO events (
                event_id, aggregate_id, aggregate_type, event_type,
                payload, metadata, occurred_at, version
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """

        values = [
            (
                str(e.event_id),
                str(e.aggregate_id),
                e.aggregate_type,
                e.event_type,
                json.dumps(e.payload),
                json.dumps(e.metadata),
                e.occurred_at,
                e.version,
            )
            for e in events
        ]

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(query, values)

    async def get_aggregate_history(
        self, aggregate_id: uuid.UUID
    ) -> List[DomainEvent]:
        """Retrieve the full event history for an aggregate, ordered by version.

        Unknown event types are skipped and logged rather than raising so that
        a single unrecognised event does not break replay of the entire stream.

        Args:
            aggregate_id: The aggregate whose history to load.

        Returns:
            Chronologically ordered, concrete ``DomainEvent`` instances.
        """
        query = """
            SELECT event_id, aggregate_id, aggregate_type, event_type,
                   payload, metadata, occurred_at, version
            FROM events
            WHERE aggregate_id = $1
            ORDER BY version ASC
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, str(aggregate_id))

        return self._rows_to_events(rows)

    async def get_events_after(
        self, position: int, limit: int = 100
    ) -> List[DomainEvent]:
        """Retrieve events globally after a given sequential position.

        Useful for event replay and building read-model projections.
        Assumes an auto-incrementing ``global_position`` column in the DB.

        Args:
            position: Exclusive lower bound on ``global_position``.
            limit:    Maximum number of events to return.

        Returns:
            Concrete ``DomainEvent`` instances, unknown types filtered out.
        """
        query = """
            SELECT event_id, aggregate_id, aggregate_type, event_type,
                   payload, metadata, occurred_at, version
            FROM events
            WHERE global_position > $1
            ORDER BY global_position ASC
            LIMIT $2
        """

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, position, limit)

        return self._rows_to_events(rows)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rows_to_events(self, rows: List[asyncpg.Record]) -> List[DomainEvent]:
        """Map a sequence of DB rows to concrete events, dropping unknowns.

        Centralises the filter-None step so each public method doesn't have
        to repeat the list-comprehension + None-guard pattern.
        """
        events: List[DomainEvent] = []
        for row in rows:
            event = self._row_to_event(row)
            if event is not None:
                events.append(event)
        return events

    def _row_to_event(self, row: asyncpg.Record) -> Optional[DomainEvent]:
        """Deserialise a single DB row into its registered concrete event class.

        Returns ``None`` (and logs a warning) if the ``event_type`` has no
        registered class.  This keeps the store forward-compatible: rows
        written by a newer service version won't crash older consumers.

        Args:
            row: An asyncpg ``Record`` with at minimum the columns selected by
                 ``get_aggregate_history`` / ``get_events_after``.

        Returns:
            A concrete ``DomainEvent`` subclass instance, or ``None``.
        """
        event_type: str = row["event_type"]

        # ------------------------------------------------------------------
        # Registry lookup — never instantiate DomainEvent directly.
        # DomainEvent is abstract; direct instantiation either raises
        # TypeError or produces an object missing subclass-specific fields.
        # ------------------------------------------------------------------
        event_cls: Optional[Type[DomainEvent]] = _EVENT_REGISTRY.get(event_type)

        if event_cls is None:
            logger.warning(
                "Unknown event_type '%s' for aggregate_id='%s' version=%s — "
                "skipping. Register the class with @register_event('%s') "
                "and ensure its module is imported at application startup.",
                event_type,
                row["aggregate_id"],
                row["version"],
                event_type,
            )
            return None

        try:
            # model_validate() runs Pydantic v2 validation + field coercion
            # on the raw dict, so each subclass's field definitions are
            # respected (types, validators, aliases, defaults).
            return event_cls.model_validate(
                {
                    "event_id": row["event_id"],
                    "aggregate_id": row["aggregate_id"],
                    "aggregate_type": row["aggregate_type"],
                    "event_type": event_type,
                    "payload": json.loads(row["payload"]),
                    "metadata": json.loads(row["metadata"]),
                    "occurred_at": row["occurred_at"],
                    "version": row["version"],
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to deserialise event_type='%s' aggregate_id='%s' "
                "version=%s: %s",
                event_type,
                row["aggregate_id"],
                row["version"],
                exc,
                exc_info=True,
            )
            return None