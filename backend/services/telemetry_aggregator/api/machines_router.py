from __future__ import annotations

import structlog
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────



class MachineOut(BaseModel):
    machine_id: str
    name: str
    type: Optional[str] = None
    location: Optional[str] = None
    factory_id: str
    active: bool
    sensor_count: int


class MachineListResponse(BaseModel):
    machines: List[MachineOut]
    count: int


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=MachineListResponse)
async def list_machines(
    request: Request,
    active_only: bool = Query(
        True, description="Si vrai, ne renvoie que les machines actives"
    ),
) -> MachineListResponse:
    """
    Liste toutes les machines connues du système, avec le nombre de capteurs
    associés à chacune.

    Cette route n'existait pas encore dans le projet : jusqu'ici, il fallait
    déjà connaître le `machine_id` exact (ex: "CNC-07") pour interroger les
    autres routes (/sensors/machines/{id}/latest, /anomalies/machines/{id}).
    Elle sert de point d'entrée pour qu'un frontend puisse d'abord demander
    "quelles machines existent ?" avant d'afficher leurs détails.
    """
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not available")

    query = """
        SELECT
            m.machine_id,
            m.name,
            m.type,
            m.location,
            m.factory_id,
            m.active,
            COUNT(s.sensor_id) AS sensor_count
        FROM machines m
        LEFT JOIN sensors s ON s.machine_id = m.machine_id
        {where_clause}
        GROUP BY m.machine_id, m.name, m.type, m.location, m.factory_id, m.active
        ORDER BY m.machine_id ASC
    """
    where_clause = "WHERE m.active = TRUE" if active_only else ""

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query.format(where_clause=where_clause))
    except Exception as exc:
        logger.error("list_machines_db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch machines")

    machines = [
        MachineOut(
            machine_id=r["machine_id"],
            name=r["name"],
            type=r["type"],
            location=r["location"],
            factory_id=r["factory_id"],
            active=r["active"],
            sensor_count=r["sensor_count"],
        )
        for r in rows
    ]

    return MachineListResponse(machines=machines, count=len(machines))
