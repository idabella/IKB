from __future__ import annotations

from fastapi import APIRouter

from backend.services.telemetry_aggregator.api.sensors_router import router as sensors_router
from backend.services.telemetry_aggregator.api.anomalies_router import router as anomalies_router
from backend.services.telemetry_aggregator.api.machines_router import router as machines_router

router = APIRouter()

router.include_router(sensors_router, prefix="/sensors", tags=["Sensors"])
router.include_router(anomalies_router, prefix="/anomalies", tags=["Anomalies"])
router.include_router(machines_router, prefix="/machines", tags=["Machines"])
