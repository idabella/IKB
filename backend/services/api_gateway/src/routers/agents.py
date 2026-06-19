"""
API Gateway — Agents Router
Forwards agent-related requests to the consolidated Knowledge Engine (port 8001).

ARCHITECTURE CHANGE:
  Before:  API Gateway → agent-service:8000  (dedicated microservice)
  After:   API Gateway → knowledge-engine:8001/api/v1/agents  (consolidated)
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["Agents"])

# ── Service URL ──────────────────────────────────────────────────────────────
# KNOWLEDGE_ENGINE_URL supersedes the old AGENT_SERVICE_URL.
# The env-var is set in docker-compose.dev.yml.
KNOWLEDGE_ENGINE_URL: str = os.environ.get(
    "KNOWLEDGE_ENGINE_URL",
    os.environ.get("AGENT_SERVICE_URL", "http://knowledge-engine:8001"),  # fallback for migration
)


def _engine_url(path: str) -> str:
    """Build the full Knowledge Engine URL for a given sub-path."""
    return f"{KNOWLEDGE_ENGINE_URL}/api/v1/agents{path}"


@router.post("/analyze")
async def submit_analysis_task(request: Request) -> Dict[str, Any]:
    """
    Submit an async agent analysis task.
    Proxies to: Knowledge Engine → POST /api/v1/agents/analyze
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant ID missing from request state")

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    payload["tenant_id"] = tenant_id
    logger.info("Submitting analysis task for tenant=%s", tenant_id)

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(_engine_url("/analyze"), json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error("Knowledge engine returned %s for /analyze: %s", exc.response.status_code, exc)
            raise HTTPException(status_code=exc.response.status_code, detail="Knowledge engine error")
        except httpx.HTTPError as exc:
            logger.error("Knowledge engine unreachable: %s", exc)
            raise HTTPException(status_code=502, detail="Knowledge engine unavailable")


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str, request: Request) -> Dict[str, Any]:
    """
    Poll task status and result.
    Proxies to: Knowledge Engine → GET /api/v1/agents/tasks/{task_id}
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant ID missing from request state")

    logger.info("Polling task=%s for tenant=%s", task_id, tenant_id)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                _engine_url(f"/tasks/{task_id}"),
                params={"tenant_id": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Task not found")
            logger.error("Knowledge engine error on task poll: %s", exc)
            raise HTTPException(status_code=502, detail="Knowledge engine error")
        except httpx.HTTPError as exc:
            logger.error("Knowledge engine unreachable on task poll: %s", exc)
            raise HTTPException(status_code=502, detail="Knowledge engine unavailable")


@router.get("/tasks/{task_id}/trace")
async def get_task_trace(task_id: str, request: Request) -> Dict[str, Any]:
    """
    Retrieve per-step tool execution trace for a completed or running task.
    Proxies to: Knowledge Engine → GET /api/v1/agents/tasks/{task_id}/trace
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant ID missing from request state")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                _engine_url(f"/tasks/{task_id}/trace"),
                params={"tenant_id": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Task not found")
            raise HTTPException(status_code=502, detail="Knowledge engine error")
        except httpx.HTTPError as exc:
            logger.error("Knowledge engine unreachable on trace request: %s", exc)
            raise HTTPException(status_code=502, detail="Knowledge engine unavailable")


@router.delete("/tasks/{task_id}")
async def cancel_task(task_id: str, request: Request) -> Dict[str, Any]:
    """
    Cancel an ongoing task.
    Proxies to: Knowledge Engine → DELETE /api/v1/agents/tasks/{task_id}
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant ID missing from request state")

    logger.info("Cancelling task=%s for tenant=%s", task_id, tenant_id)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.delete(
                _engine_url(f"/tasks/{task_id}"),
                params={"tenant_id": tenant_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Task not found")
            raise HTTPException(status_code=502, detail="Knowledge engine error")
        except httpx.HTTPError as exc:
            logger.error("Knowledge engine unreachable on cancel: %s", exc)
            raise HTTPException(status_code=502, detail="Knowledge engine unavailable")
