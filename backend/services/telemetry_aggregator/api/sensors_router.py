from __future__ import annotations

import datetime
import structlog
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.shared.security.rbac import require_roles, Roles

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class SensorReadingIn(BaseModel):
    sensor_id:  str
    machine_id: str
    tenant_id:  str = "default"
    value:      float
    unit:       str = ""
    quality:    int = Field(default=100, ge=0, le=100)
    timestamp:  Optional[float] = None


class SensorReadingOut(SensorReadingIn):
    received_at: str


class LatestReadingsResponse(BaseModel):
    machine_id: str
    readings:   List[Dict[str, Any]]
    count:      int


class TimeSeriesPoint(BaseModel):
    time:      str
    value:     float
    sensor_id: str


class TimeSeriesResponse(BaseModel):
    machine_id: str
    sensor_id:  str
    start:      str
    end:        str
    points:     List[TimeSeriesPoint]
    source:     str = "timescaledb"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_window(window: str) -> datetime.timedelta:
    """Parse compact window strings like '1h', '6h', '24h', '7d'."""
    unit = window[-1].lower()
    n    = int(window[:-1])
    return {"h": datetime.timedelta(hours=n), "d": datetime.timedelta(days=n)}.get(
        unit, datetime.timedelta(hours=1)
    )


def _get_db_pool(request: Request) -> asyncpg.Pool:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not ready")
    return pool


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/readings", response_model=SensorReadingOut, status_code=201)
async def ingest_reading(
    reading: SensorReadingIn,
    request: Request,
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN, Roles.API_CLIENT])),
) -> SensorReadingOut:
    """
    Ingest a single sensor reading via REST (low-frequency path).
    High-frequency streams should go via Kafka → ikb.sensors.raw topic.

    Writes directly to TimescaleDB sensor_readings hypertable.
    Also updates the Redis latest-value cache via TelemetryRedisCache.
    """
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    ts  = reading.timestamp or now.timestamp()
    recorded_at = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)

    db_pool = _get_db_pool(request)

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO sensor_readings
                (sensor_id, machine_id, tenant_id, value, unit, quality, recorded_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            reading.sensor_id,
            reading.machine_id,
            reading.tenant_id,
            reading.value,
            reading.unit,
            reading.quality,
            recorded_at,
        )

    # Update Redis latest-value cache (best-effort — non-blocking)
    try:
        processor = getattr(request.app.state, "stream_processor", None)
        if processor and hasattr(processor, "redis_cache") and processor.redis_cache:
            await processor.redis_cache.set_latest(
                reading.machine_id,
                reading.sensor_id,
                {
                    "value": reading.value,
                    "unit":  reading.unit,
                    "ts":    ts,
                },
            )
    except Exception as exc:
        logger.warning("redis_cache_update_skipped", error=str(exc))

    logger.info(
        "rest_sensor_ingest",
        machine_id=reading.machine_id,
        sensor_id=reading.sensor_id,
        value=reading.value,
    )
    return SensorReadingOut(
        **reading.model_dump(),
        timestamp=ts,
        received_at=recorded_at.isoformat(),
    )


@router.get("/machines/{machine_id}/latest", response_model=LatestReadingsResponse)
async def get_latest_readings(
    machine_id: str,
    request: Request,
    limit: int = Query(20, ge=1, le=200),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
) -> LatestReadingsResponse:
    """
    Return the most recent sensor readings for a machine.

    Served from Redis cache (TTL 30s) for sub-millisecond response.
    Falls back to TimescaleDB latest_sensor_readings view if cache is cold.
    """
    # L1: Redis cache
    try:
        processor = getattr(request.app.state, "stream_processor", None)
        if processor and hasattr(processor, "redis_cache") and processor.redis_cache:
            readings = await processor.redis_cache.get_latest(machine_id, limit=limit)
            if readings:
                return LatestReadingsResponse(
                    machine_id=machine_id,
                    readings=readings,
                    count=len(readings),
                )
    except Exception as exc:
        logger.warning("redis_latest_cache_miss", machine_id=machine_id, error=str(exc))

    # L2: TimescaleDB fallback
    try:
        db_pool = _get_db_pool(request)
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT sensor_id, value, unit, recorded_at
                FROM   latest_sensor_readings
                WHERE  machine_id = $1
                LIMIT  $2
                """,
                machine_id,
                limit,
            )
        readings = [
            {
                "sensor_id":   r["sensor_id"],
                "value":       r["value"],
                "unit":        r["unit"],
                "recorded_at": r["recorded_at"].isoformat(),
            }
            for r in rows
        ]
        return LatestReadingsResponse(
            machine_id=machine_id,
            readings=readings,
            count=len(readings),
        )
    except Exception as exc:
        logger.error("latest_readings_db_error", machine_id=machine_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch latest readings")


@router.get(
    "/machines/{machine_id}/sensors/{sensor_id}/history",
    response_model=TimeSeriesResponse,
)
async def get_sensor_history(
    machine_id: str,
    sensor_id:  str,
    request: Request,
    start:  Optional[str] = Query(None, description="ISO-8601 start datetime"),
    end:    Optional[str] = Query(None, description="ISO-8601 end datetime"),
    window: str = Query("1h", description="Lookback window if start/end not provided: 1h, 6h, 24h, 7d"),
    bucket: str = Query("5m", description="Aggregation bucket size for hourly+ windows"),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
) -> TimeSeriesResponse:
    """
    Query historical time-series from TimescaleDB.

    - Windows < 1 day: raw sensor_readings (per-reading granularity)
    - Windows ≥ 1 day: sensor_readings_hourly continuous aggregate (pre-computed)
    """
    now    = datetime.datetime.now(tz=datetime.timezone.utc)
    end_dt = datetime.datetime.fromisoformat(end) if end else now

    if start:
        start_dt = datetime.datetime.fromisoformat(start)
    else:
        start_dt = end_dt - _parse_window(window)

    duration_hours = (end_dt - start_dt).total_seconds() / 3600

    db_pool = _get_db_pool(request)

    try:
        async with db_pool.acquire() as conn:
            if duration_hours <= 24:
                # Raw readings — fine-grained
                rows = await conn.fetch(
                    """
                    SELECT recorded_at AS time, value
                    FROM   sensor_readings
                    WHERE  machine_id  = $1
                      AND  sensor_id   = $2
                      AND  recorded_at BETWEEN $3 AND $4
                    ORDER  BY recorded_at ASC
                    LIMIT  10000
                    """,
                    machine_id, sensor_id, start_dt, end_dt,
                )
            else:
                # Hourly aggregate — pre-computed by TimescaleDB background worker
                rows = await conn.fetch(
                    """
                    SELECT bucket AS time, avg_val AS value
                    FROM   sensor_readings_hourly
                    WHERE  machine_id = $1
                      AND  sensor_id  = $2
                      AND  bucket     BETWEEN $3 AND $4
                    ORDER  BY bucket ASC
                    """,
                    machine_id, sensor_id, start_dt, end_dt,
                )

    except Exception as exc:
        logger.error(
            "timescaledb_history_query_failed",
            machine_id=machine_id,
            sensor_id=sensor_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Time-series query error")

    points = [
        TimeSeriesPoint(
            time=r["time"].isoformat() if hasattr(r["time"], "isoformat") else str(r["time"]),
            value=r["value"],
            sensor_id=sensor_id,
        )
        for r in rows
    ]

    return TimeSeriesResponse(
        machine_id=machine_id,
        sensor_id=sensor_id,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        points=points,
    )
