"""
Alerts router — list, acknowledge, resolve, add technician notes.
"""

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

try:
    from database import get_session
    from models import Alert, AlertRead
except ImportError:
    from backend.database import get_session
    from backend.models import Alert, AlertRead

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _alert_to_read(a: Alert) -> AlertRead:
    return AlertRead(
        id=a.id,
        machine=a.machine,
        type=a.type,
        description=a.description,
        severity=a.severity,
        status=a.status,
        current=a.current,
        threshold=a.threshold,
        duration=a.duration,
        time=a.time,
        full_time=a.full_time,
        tags=json.loads(a.tags_json),
        assigned_to=a.assigned_to,
        notes=a.notes,
    )


@router.get("", response_model=List[AlertRead])
def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    machine: Optional[str] = None,
    session: Session = Depends(get_session),
):
    query = select(Alert)
    if status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)
    if machine:
        query = query.where(Alert.machine == machine)
    alerts = session.exec(query).all()
    return [_alert_to_read(a) for a in alerts]


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(alert_id: str, session: Session = Depends(get_session)):
    a = session.get(Alert, alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _alert_to_read(a)


@router.post("/{alert_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(alert_id: str, session: Session = Depends(get_session)):
    a = session.get(Alert, alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    if a.status == "resolved":
        raise HTTPException(status_code=400, detail="Cannot acknowledge a resolved alert")
    a.status = "acknowledged"
    session.add(a)
    session.commit()
    session.refresh(a)
    return _alert_to_read(a)


@router.post("/{alert_id}/resolve", response_model=AlertRead)
def resolve_alert(alert_id: str, session: Session = Depends(get_session)):
    a = session.get(Alert, alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    a.status = "resolved"
    session.add(a)
    session.commit()
    session.refresh(a)
    return _alert_to_read(a)


class NoteBody(BaseModel):
    note: str


@router.post("/{alert_id}/note", response_model=AlertRead)
def add_note(alert_id: str, body: NoteBody, session: Session = Depends(get_session)):
    a = session.get(Alert, alert_id)
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    existing = a.notes or ""
    a.notes = f"{existing}\n[{timestamp}] {body.note}".strip()
    session.add(a)
    session.commit()
    session.refresh(a)
    return _alert_to_read(a)
