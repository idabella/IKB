"""
Seed the database with the same data that was previously in src/lib/mock-data.ts.
Run once:  python -m backend.seed
"""

import json
import sys
import os

# Allow running as a standalone script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlmodel import Session, select

from backend.database import create_db_and_tables, engine
from backend.models import (
    Machine,
    Alert,
    Document,
    Insight,
    ActivityEvent,
    VibrationPoint,
)

# ---------------------------------------------------------------------------
# Seed data (mirrors mock-data.ts exactly)
# ---------------------------------------------------------------------------

MACHINES = [
    dict(id="m1", name="CNC Mill #1", type="CNC Milling Machine", status="online",
         last_check="5 min ago", efficiency=94, temp=62, vibration=1.8, rpm=1500,
         pressure=2.4, serial="CNCM-2021-001", installed="2021-03-12",
         location="Hall A", department="Production"),
    dict(id="m2", name="CNC Mill #3", type="CNC Milling Machine", status="alert",
         last_check="2 min ago", efficiency=67, temp=68, vibration=4.1, rpm=1450,
         pressure=2.3, serial="CNCM-2021-003", installed="2021-03-15",
         location="Hall A", department="Production"),
    dict(id="m3", name="Hydraulic Press #2", type="Hydraulic Press", status="online",
         last_check="15 min ago", efficiency=91, temp=55, vibration=1.2, rpm=0,
         pressure=180, serial="HP-2020-002", installed="2020-07-22",
         location="Hall B", department="Forming"),
    dict(id="m4", name="Compressor #4", type="Air Compressor", status="warning",
         last_check="30 min ago", efficiency=78, temp=71, vibration=2.4, rpm=2900,
         pressure=8.2, serial="CMP-2019-004", installed="2019-11-04",
         location="Utility Room", department="Utilities"),
    dict(id="m5", name="Lathe #5", type="CNC Lathe", status="online",
         last_check="1 hr ago", efficiency=88, temp=58, vibration=1.5, rpm=1800,
         pressure=2.1, serial="LTH-2022-005", installed="2022-02-18",
         location="Hall A", department="Production"),
    dict(id="m6", name="Welding Robot #2", type="Robotic Welder", status="online",
         last_check="3 min ago", efficiency=96, temp=49, vibration=0.9, rpm=0,
         pressure=1.8, serial="WR-2022-002", installed="2022-08-30",
         location="Hall C", department="Assembly"),
]

ALERTS = [
    dict(id="a1", machine="CNC Mill #3", type="Vibration Anomaly",
         description="Vibration levels exceeded the defined threshold for more than 2 consecutive minutes",
         severity="high", status="active", current="4.1 mm/s", threshold="3.5 mm/s",
         duration="Active for 8 minutes", time="2 min ago",
         full_time="2026-04-22 11:15:42",
         tags_json=json.dumps(["CNC Milling", "Production", "Hall A"]),
         assigned_to="M. Laurent", notes=None),
    dict(id="a2", machine="Compressor #4", type="Pressure Warning",
         description="Output pressure trending above safe operational range",
         severity="medium", status="active", current="8.2 bar", threshold="8.0 bar",
         duration="Active for 14 minutes", time="14 min ago",
         full_time="2026-04-22 11:03:11",
         tags_json=json.dumps(["Compressor", "Utilities"]),
         assigned_to="Unassigned", notes=None),
    dict(id="a3", machine="Hydraulic Press #1", type="Temperature Spike",
         description="Hydraulic fluid temperature briefly exceeded 75°C",
         severity="low", status="acknowledged", current="76°C", threshold="75°C",
         duration="Resolved after 4 min", time="1 hr ago",
         full_time="2026-04-22 10:14:00",
         tags_json=json.dumps(["Hydraulic Press", "Forming"]),
         assigned_to="S. Dupont", notes=None),
]

DOCUMENTS = [
    dict(id="d1", title="FMEA — CNC Milling Spindle Unit 2023", type="PDF", category="FMEA",
         excerpt="Failure modes and effects analysis for spindle assembly including bearing wear, lubrication faults, and thermal expansion.",
         machines_json=json.dumps(["CNC Mill #1", "CNC Mill #3"]),
         date="2023-09-12", author="R. Mercier"),
    dict(id="d2", title="Bearing Replacement Procedure — Spindle Axis", type="PDF", category="Procedure",
         excerpt="Step-by-step torque sequence and alignment checks for spindle bearing replacement on CNC milling units.",
         machines_json=json.dumps(["CNC Mill #1", "CNC Mill #3", "Lathe #5"]),
         date="2024-01-04", author="L. Bernard"),
    dict(id="d3", title="Incident Report — Compressor #4 Pressure Excursion", type="DOCX", category="Incident Report",
         excerpt="Root cause analysis of pressure relief valve drift identified during Q1 2024 inspection cycle.",
         machines_json=json.dumps(["Compressor #4"]),
         date="2024-02-19", author="A. Klein"),
    dict(id="d4", title="Standard Operating Procedure — Lathe Tool Change", type="PDF", category="SOP",
         excerpt="Safe practices for changing turning tools, including chuck verification and feed rate calibration.",
         machines_json=json.dumps(["Lathe #5"]),
         date="2023-11-22", author="P. Nguyen"),
    dict(id="d5", title="Predictive Maintenance Training Module 4", type="PDF", category="Training",
         excerpt="Vibration signature interpretation and trending techniques for rotating equipment.",
         machines_json=json.dumps(["CNC Mill #1", "Lathe #5", "Compressor #4"]),
         date="2024-03-08", author="Training Dept."),
    dict(id="d6", title="Hydraulic Press Maintenance Schedule 2024", type="DOCX", category="Procedure",
         excerpt="Quarterly maintenance plan including seal inspection, fluid analysis, and pressure calibration intervals.",
         machines_json=json.dumps(["Hydraulic Press #2"]),
         date="2024-01-15", author="T. Okafor"),
]

INSIGHTS = [
    dict(id="i1", title="Predictive Maintenance Alert",
         desc="CNC Mill #3 bearing wear pattern suggests replacement needed within 72 hours.",
         time="12 min ago"),
    dict(id="i2", title="Efficiency Opportunity",
         desc="Compressor #4 idle cycles increased 14%. Adjusting load thresholds could save ~3.1% energy.",
         time="1 hr ago"),
    dict(id="i3", title="Pattern Detected",
         desc="Vibration spikes on CNC Mill #3 correlate with shift changeover at 11:00. Investigate handoff procedure.",
         time="2 hr ago"),
]

ACTIVITY = [
    dict(id="r1", machine="CNC Mill #1", desc="Normal operation", time="2 min ago", kind="ok"),
    dict(id="r2", machine="CNC Mill #3", desc="Vibration spike detected", time="8 min ago", kind="warn"),
    dict(id="r3", machine="Hydraulic Press #2", desc="Maintenance completed", time="1 hr ago", kind="ok"),
    dict(id="r4", machine="Compressor #4", desc="Pressure warning", time="2 hr ago", kind="danger"),
]

VIBRATION = [
    dict(machine_id="m2", time="10:15", value=1.8),
    dict(machine_id="m2", time="10:20", value=2.1),
    dict(machine_id="m2", time="10:25", value=2.0),
    dict(machine_id="m2", time="10:30", value=2.4),
    dict(machine_id="m2", time="10:35", value=2.2),
    dict(machine_id="m2", time="10:40", value=2.7),
    dict(machine_id="m2", time="10:45", value=3.0),
    dict(machine_id="m2", time="10:50", value=2.9),
    dict(machine_id="m2", time="10:55", value=3.3),
    dict(machine_id="m2", time="11:00", value=3.6),
    dict(machine_id="m2", time="11:05", value=3.8),
    dict(machine_id="m2", time="11:10", value=3.9),
    dict(machine_id="m2", time="11:15", value=4.1),
]


# ---------------------------------------------------------------------------
# Seeder
# ---------------------------------------------------------------------------

def seed():
    create_db_and_tables()
    with Session(engine) as session:
        # Skip if already seeded
        existing = session.exec(select(Machine)).first()
        if existing:
            print("Database already seeded — skipping.")
            return

        for row in MACHINES:
            session.add(Machine(**row))
        for row in ALERTS:
            session.add(Alert(**row))
        for row in DOCUMENTS:
            session.add(Document(**row))
        for row in INSIGHTS:
            session.add(Insight(**row))
        for row in ACTIVITY:
            session.add(ActivityEvent(**row))
        for row in VIBRATION:
            session.add(VibrationPoint(**row))

        session.commit()
        print(f"[OK] Seeded {len(MACHINES)} machines, {len(ALERTS)} alerts, "
              f"{len(DOCUMENTS)} documents, {len(INSIGHTS)} insights, "
              f"{len(ACTIVITY)} activity events, {len(VIBRATION)} vibration points.")


if __name__ == "__main__":
    seed()
