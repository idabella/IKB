from __future__ import annotations

import structlog
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request, HTTPException
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter()


class AnomalyEvent(BaseModel):
    anomaly_id: str
    machine_id: str
    sensor_id: str
    severity: str
    value: float
    timestamp: float
    detector_type: str
    description: Optional[str] = None


class AnomalyListResponse(BaseModel):
    machine_id: str
    anomalies: List[Dict[str, Any]]
    count: int


@router.get("/machines/{machine_id}", response_model=AnomalyListResponse)
async def list_anomalies(
    machine_id: str,
    request: Request,
    severity: Optional[str] = Query(None, description="Filter by severity: LOW, MEDIUM, HIGH, CRITICAL"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> AnomalyListResponse:
    """
    List recent anomaly events for a machine.
    Results are fetched from the PostgreSQL anomaly_events table.
    """
    from backend.shared.infrastructure.database.postgres import get_db_pool

    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")

    async with pool.acquire() as conn:
        if severity:
            rows = await conn.fetch(
                """
                SELECT anomaly_id, machine_id, sensor_id, severity, value,
                       EXTRACT(EPOCH FROM detected_at)::float AS timestamp,
                       detector_type, description
                FROM anomaly_events
                WHERE machine_id = $1 AND severity = $2
                ORDER BY detected_at DESC
                LIMIT $3 OFFSET $4
                """,
                machine_id,
                severity.upper(),
                limit,
                offset,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT anomaly_id, machine_id, sensor_id, severity, value,
                       EXTRACT(EPOCH FROM detected_at)::float AS timestamp,
                       detector_type, description
                FROM anomaly_events
                WHERE machine_id = $1
                ORDER BY detected_at DESC
                LIMIT $2 OFFSET $3
                """,
                machine_id,
                limit,
                offset,
            )

    anomalies = [dict(r) for r in rows]
    return AnomalyListResponse(machine_id=machine_id, anomalies=anomalies, count=len(anomalies))


@router.get("/{anomaly_id}", response_model=AnomalyEvent)
async def get_anomaly(anomaly_id: str, request: Request) -> AnomalyEvent:
    """Retrieve a single anomaly event by ID."""
    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT anomaly_id, machine_id, sensor_id, severity, value,
                   EXTRACT(EPOCH FROM detected_at)::float AS timestamp,
                   detector_type, description
            FROM anomaly_events
            WHERE anomaly_id = $1
            """,
            anomaly_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail="Anomaly event not found")

    return AnomalyEvent(**dict(row))
