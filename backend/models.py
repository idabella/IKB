"""
SQLModel table definitions for the Industrial Insight Hub backend.
All tables mirror the TypeScript types in src/lib/mock-data.ts.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from sqlmodel import Field, SQLModel


# ---------------------------------------------------------------------------
# Machine
# ---------------------------------------------------------------------------

class MachineBase(SQLModel):
    name: str
    type: str
    status: str = "online"          # online | alert | warning | maintenance
    last_check: str = "just now"
    efficiency: float = 100.0
    temp: float = 50.0
    vibration: float = 1.0
    rpm: int = 0
    pressure: float = 1.0
    serial: str = ""
    installed: str = ""
    location: str = ""
    department: str = ""


class Machine(MachineBase, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[str] = Field(default=None, primary_key=True)


class MachineCreate(MachineBase):
    id: str


class MachineRead(MachineBase):
    id: str


class MachineUpdate(SQLModel):
    name: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    last_check: Optional[str] = None
    efficiency: Optional[float] = None
    temp: Optional[float] = None
    vibration: Optional[float] = None
    rpm: Optional[int] = None
    pressure: Optional[float] = None
    serial: Optional[str] = None
    installed: Optional[str] = None
    location: Optional[str] = None
    department: Optional[str] = None


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

class AlertBase(SQLModel):
    machine: str
    type: str
    description: str
    severity: str = "medium"        # high | medium | low
    status: str = "active"          # active | acknowledged | resolved
    current: str = ""
    threshold: str = ""
    duration: str = ""
    time: str = ""
    full_time: str = ""
    tags_json: str = "[]"           # JSON-encoded list[str]
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class Alert(AlertBase, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[str] = Field(default=None, primary_key=True)


class AlertRead(SQLModel):
    id: str
    machine: str
    type: str
    description: str
    severity: str
    status: str
    current: str
    threshold: str
    duration: str
    time: str
    full_time: str
    tags: List[str]
    assigned_to: Optional[str]
    notes: Optional[str]


class AlertCreate(AlertBase):
    id: str


# ---------------------------------------------------------------------------
# Document (Knowledge Base)
# ---------------------------------------------------------------------------

class DocumentBase(SQLModel):
    title: str
    type: str = "PDF"               # PDF | DOCX
    category: str = "Documents"     # FMEA | Procedure | Incident Report | SOP | Training
    excerpt: str = ""
    machines_json: str = "[]"       # JSON-encoded list[str]
    date: str = ""
    author: str = ""


class Document(DocumentBase, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[str] = Field(default=None, primary_key=True)


class DocumentRead(SQLModel):
    id: str
    title: str
    type: str
    category: str
    excerpt: str
    machines: List[str]
    date: str
    author: str


class DocumentCreate(DocumentBase):
    id: str


# ---------------------------------------------------------------------------
# Insight
# ---------------------------------------------------------------------------

class InsightBase(SQLModel):
    title: str
    desc: str
    time: str = ""


class Insight(InsightBase, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[str] = Field(default=None, primary_key=True)


class InsightRead(InsightBase):
    id: str


# ---------------------------------------------------------------------------
# ActivityEvent
# ---------------------------------------------------------------------------

class ActivityEventBase(SQLModel):
    machine: str
    desc: str
    time: str = ""
    kind: str = "ok"                # ok | warn | danger


class ActivityEvent(ActivityEventBase, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[str] = Field(default=None, primary_key=True)


class ActivityEventRead(ActivityEventBase):
    id: str


# ---------------------------------------------------------------------------
# VibrationPoint  (time-series for dashboard chart)
# ---------------------------------------------------------------------------

class VibrationPoint(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    machine_id: str
    time: str
    value: float


class VibrationPointRead(SQLModel):
    time: str
    value: float


# ---------------------------------------------------------------------------
# ChatMessage  (conversation history)
# ---------------------------------------------------------------------------

class ChatMessage(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    role: str           # user | ai
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
