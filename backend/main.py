"""
Industrial Insight Hub — FastAPI backend entry point.

Start:
    cd industrial-insight-hub
    python -m backend.seed          # first time only
    uvicorn backend.main:app --reload --port 3000

OpenAPI docs:  http://localhost:3000/docs
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    # Launched from backend/ directory: uvicorn main:app
    from database import create_db_and_tables
    from routes import machines, alerts, documents, dashboard, chat
except ImportError:
    # Launched from project root: uvicorn backend.main:app
    from backend.database import create_db_and_tables
    from backend.routes import machines, alerts, documents, dashboard, chat

app = FastAPI(
    title="Industrial Insight Hub API",
    version="1.0.0",
    description="Real-time industrial operations monitoring — machines, alerts, knowledge base, and AI chat.",
)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server and any local origin
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Standard Vite ports
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:5176",
        "http://localhost:5177",
        "http://localhost:5178",
        "http://localhost:5179",
        "http://localhost:5180",
        "http://localhost:3000",
        "http://localhost:4173",   # Vite preview
        "http://localhost:8080",   # Sandbox/alternative
        "http://localhost:8081",   # Vite fallback port
        "http://localhost:8082",   # Vite fallback port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup: create tables + seed if empty
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    create_db_and_tables()


# ---------------------------------------------------------------------------
# Mount routers
# ---------------------------------------------------------------------------

app.include_router(machines.router)
app.include_router(alerts.router)
app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(chat.router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok", "service": "Industrial Insight Hub API"}
