"""
knowledge_engine/api/dependencies.py

Centralised FastAPI Depends() singletons for the Knowledge Engine.

All routers import from here instead of calling getattr(request.app.state, ...)
directly. This:
  - Makes the dependency explicit in the function signature
  - Returns a 503 with a clear message if the service is still starting
  - Makes unit testing easy: override with app.dependency_overrides[get_orchestrator]
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
import asyncpg


# ── Agent Orchestrator ────────────────────────────────────────────────────────

def get_orchestrator(request: Request):
    """
    Inject the singleton AgentOrchestrator built in main.py lifespan.
    Raises 503 if the service hasn't finished starting.
    """
    obj = getattr(request.app.state, "orchestrator", None)
    if obj is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "SERVICE_NOT_READY",
                "message": "AgentOrchestrator is initialising — try again in a moment",
            },
        )
    return obj


# ── RAG Retrieval Handler ─────────────────────────────────────────────────────

def get_retrieve_handler(request: Request):
    """Inject the singleton RetrieveContextHandler."""
    obj = getattr(request.app.state, "retrieve_handler", None)
    if obj is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "SERVICE_NOT_READY",
                "message": "RetrieveContextHandler is initialising — try again in a moment",
            },
        )
    return obj


# ── Document Ingestion Handler ────────────────────────────────────────────────

def get_ingest_handler(request: Request):
    """Inject the singleton IngestDocumentHandler."""
    obj = getattr(request.app.state, "ingest_handler", None)
    if obj is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "SERVICE_NOT_READY",
                "message": "IngestDocumentHandler is initialising — try again in a moment",
            },
        )
    return obj


# ── PostgreSQL Pool ───────────────────────────────────────────────────────────

async def get_db(request: Request) -> asyncpg.Pool:
    """Inject the shared asyncpg connection pool."""
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "SERVICE_NOT_READY",
                "message": "Database pool is initialising",
            },
        )
    return pool


# ── Convenience re-export for test overrides ──────────────────────────────────

__all__ = [
    "get_orchestrator",
    "get_retrieve_handler",
    "get_ingest_handler",
    "get_db",
]
