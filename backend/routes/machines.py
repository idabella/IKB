"""
Machines router — CRUD + simulated live sensor readings.
"""

import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

try:
    from database import get_session
    from models import Machine, MachineCreate, MachineRead, MachineUpdate
except ImportError:
    from backend.database import get_session
    from backend.models import Machine, MachineCreate, MachineRead, MachineUpdate

router = APIRouter(prefix="/api/machines", tags=["machines"])


def _add_noise(value: float, pct: float = 0.03) -> float:
    """Add ±pct random noise to simulate live sensor drift."""
    delta = value * pct
    return round(value + random.uniform(-delta, delta), 2)


def _machine_to_read(m: Machine) -> MachineRead:
    """Return a MachineRead, adding small sensor noise to simulate live data."""
    return MachineRead(
        id=m.id,
        name=m.name,
        type=m.type,
        status=m.status,
        last_check=m.last_check,
        efficiency=round(_add_noise(m.efficiency, 0.01), 1),
        temp=round(_add_noise(m.temp, 0.02), 1),
        vibration=round(_add_noise(m.vibration, 0.04), 2),
        rpm=int(_add_noise(m.rpm, 0.02)) if m.rpm else 0,
        pressure=round(_add_noise(m.pressure, 0.03), 2),
        serial=m.serial,
        installed=m.installed,
        location=m.location,
        department=m.department,
    )


@router.get("", response_model=List[MachineRead])
def list_machines(
    status: Optional[str] = None,
    type: Optional[str] = None,
    session: Session = Depends(get_session),
):
    query = select(Machine)
    if status:
        query = query.where(Machine.status == status)
    if type:
        query = query.where(Machine.type == type)
    machines = session.exec(query).all()
    return [_machine_to_read(m) for m in machines]


@router.get("/{machine_id}", response_model=MachineRead)
def get_machine(machine_id: str, session: Session = Depends(get_session)):
    m = session.get(Machine, machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    return _machine_to_read(m)


@router.post("", response_model=MachineRead, status_code=201)
def create_machine(machine: MachineCreate, session: Session = Depends(get_session)):
    db_machine = Machine.model_validate(machine)
    session.add(db_machine)
    session.commit()
    session.refresh(db_machine)
    return _machine_to_read(db_machine)


@router.patch("/{machine_id}", response_model=MachineRead)
def update_machine(
    machine_id: str,
    update: MachineUpdate,
    session: Session = Depends(get_session),
):
    m = session.get(Machine, machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    data = update.model_dump(exclude_unset=True)
    for key, val in data.items():
        setattr(m, key, val)
    session.add(m)
    session.commit()
    session.refresh(m)
    return _machine_to_read(m)


@router.delete("/{machine_id}", status_code=204)
def delete_machine(machine_id: str, session: Session = Depends(get_session)):
    m = session.get(Machine, machine_id)
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    session.delete(m)
    session.commit()
