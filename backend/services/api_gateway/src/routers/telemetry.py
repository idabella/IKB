"""
API Gateway — Telemetry Router
Proxies sensor and anomaly endpoints to the Telemetry Aggregator (port 8002).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Telemetry"])

TELEMETRY_AGGREGATOR_URL: str = os.environ.get(
    "TELEMETRY_AGGREGATOR_URL",
    os.environ.get("TELEMETRY_SERVICE_URL", "http://telemetry-aggregator:8002"),
)


def _ta_url(path: str) -> str:
    return f"{TELEMETRY_AGGREGATOR_URL}/api/v1{path}"


async def _proxy(request: Request, method: str, path: str) -> Any:
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant ID missing from request state")

    headers = {"X-Tenant-ID": tenant_id}
    auth = request.headers.get("Authorization")
    if auth:
        headers["Authorization"] = auth

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method,
                _ta_url(path),
                headers=headers,
                params=dict(request.query_params),
                content=await request.body() if method in {"POST", "PUT", "PATCH"} else None,
            )
            response.raise_for_status()
            if response.content:
                return response.json()
            return {}
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=exc.response.text)
        except httpx.HTTPError as exc:
            logger.error("Telemetry aggregator unreachable: %s", exc)
            raise HTTPException(status_code=502, detail="Telemetry aggregator unavailable")


@router.post("/sensors/readings")
async def ingest_sensor_reading(request: Request) -> Dict[str, Any]:
    return await _proxy(request, "POST", "/sensors/readings")


@router.get("/sensors/machines/{machine_id}/latest")
async def latest_sensor_readings(machine_id: str, request: Request) -> Dict[str, Any]:
    return await _proxy(request, "GET", f"/sensors/machines/{machine_id}/latest")


@router.get("/sensors/machines/{machine_id}/sensors/{sensor_id}/history")
async def sensor_history(machine_id: str, sensor_id: str, request: Request) -> Dict[str, Any]:
    return await _proxy(request, "GET", f"/sensors/machines/{machine_id}/sensors/{sensor_id}/history")


@router.get("/anomalies/machines/{machine_id}")
async def list_anomalies(machine_id: str, request: Request) -> Dict[str, Any]:
    return await _proxy(request, "GET", f"/anomalies/machines/{machine_id}")


@router.get("/anomalies/{anomaly_id}")
async def get_anomaly(anomaly_id: str, request: Request) -> Dict[str, Any]:
    return await _proxy(request, "GET", f"/anomalies/{anomaly_id}")
