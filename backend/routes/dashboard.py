"""
Dashboard router — KPIs, vibration chart, insights feed, activity feed.
"""

import random
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select, func

try:
    from database import get_session
    from models import (
        Machine, Alert, Insight, InsightRead,
        ActivityEvent, ActivityEventRead,
        VibrationPoint, VibrationPointRead,
    )
except ImportError:
    from backend.database import get_session
    from backend.models import (
        Machine, Alert, Insight, InsightRead,
        ActivityEvent, ActivityEventRead,
        VibrationPoint, VibrationPointRead,
    )

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

class KpiResponse(BaseModel):
    active_machines: int
    active_alerts: int
    efficiency_rate: float          # average across all machines
    insight_count: int              # total insights this month
    machines_in_warning: int
    machines_in_maintenance: int


@router.get("/kpis", response_model=KpiResponse)
def get_kpis(session: Session = Depends(get_session)):
    machines = session.exec(select(Machine)).all()
    alerts = session.exec(select(Alert).where(Alert.status == "active")).all()
    insights = session.exec(select(Insight)).all()

    active = [m for m in machines if m.status == "online"]
    avg_eff = (
        round(sum(m.efficiency for m in machines) / len(machines), 1)
        if machines else 0.0
    )

    return KpiResponse(
        active_machines=len(active),
        active_alerts=len(alerts),
        efficiency_rate=avg_eff,
        insight_count=len(insights),
        machines_in_warning=sum(1 for m in machines if m.status == "warning"),
        machines_in_maintenance=sum(1 for m in machines if m.status == "maintenance"),
    )


# ---------------------------------------------------------------------------
# Vibration chart  (CNC Mill #3 = "m2")
# ---------------------------------------------------------------------------

class VibrationResponse(BaseModel):
    machine_id: str
    machine_name: str
    threshold: float
    data: List[VibrationPointRead]


@router.get("/vibration", response_model=VibrationResponse)
def get_vibration(
    machine_id: str = "m2",
    session: Session = Depends(get_session),
):
    machine = session.get(Machine, machine_id)
    points = session.exec(
        select(VibrationPoint).where(VibrationPoint.machine_id == machine_id)
    ).all()

    # Add a little live noise to the last point
    data = [VibrationPointRead(time=p.time, value=p.value) for p in points]
    if data:
        last = data[-1]
        noise = round(last.value + random.uniform(-0.05, 0.12), 2)
        data[-1] = VibrationPointRead(time=last.time, value=noise)

    return VibrationResponse(
        machine_id=machine_id,
        machine_name=machine.name if machine else machine_id,
        threshold=3.5,
        data=data,
    )


# ---------------------------------------------------------------------------
# AI Insights feed
# ---------------------------------------------------------------------------

@router.get("/insights", response_model=List[InsightRead])
def get_insights(session: Session = Depends(get_session)):
    return session.exec(select(Insight)).all()


# ---------------------------------------------------------------------------
# Recent Activity feed
# ---------------------------------------------------------------------------

@router.get("/activity", response_model=List[ActivityEventRead])
def get_activity(session: Session = Depends(get_session)):
    return session.exec(select(ActivityEvent)).all()
