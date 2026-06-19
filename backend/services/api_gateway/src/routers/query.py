"""
API Gateway — Query Router
Forwards natural-language query requests to the consolidated Knowledge Engine (port 8001),
polls for completion, and maps the async agent result to a synchronous QueryResponse.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from typing import List

import httpx
from fastapi import APIRouter, HTTPException, Request

from backend.services.api_gateway.src.schemas.query import (
    QueryRequest,
    QueryResponse,
    SourceReference,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/query", tags=["Query"])

KNOWLEDGE_ENGINE_URL: str = os.environ.get(
    "KNOWLEDGE_ENGINE_URL",
    os.environ.get("AGENT_SERVICE_URL", "http://knowledge-engine:8001"),
)


@router.post("", response_model=QueryResponse)
async def execute_query(req: QueryRequest, request: Request) -> QueryResponse:
    start_time = time.time()

    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant ID missing from request state")

    session_id = req.session_id or str(uuid.uuid4())
    payload = {
        "query": req.query,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "task_type": req.mode.value.lower(),
        "metadata": {
            "machine_ids": req.machine_ids or [],
            "time_range": req.time_range,
            "use_agents": req.use_agents,
            "max_tokens": req.max_tokens,
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            submit = await client.post(
                f"{KNOWLEDGE_ENGINE_URL}/api/v1/agents/analyze",
                json=payload,
            )
            submit.raise_for_status()
            task_id = submit.json()["task_id"]
        except httpx.HTTPError as exc:
            logger.error("Knowledge engine unreachable: %s", exc)
            raise HTTPException(status_code=502, detail="Knowledge engine unavailable")

        result_data = None
        for _ in range(90):
            await asyncio.sleep(1)
            try:
                status_resp = await client.get(
                    f"{KNOWLEDGE_ENGINE_URL}/api/v1/agents/tasks/{task_id}",
                )
                status_resp.raise_for_status()
                task = status_resp.json()
            except httpx.HTTPError as exc:
                logger.error("Task poll failed: %s", exc)
                raise HTTPException(status_code=502, detail="Knowledge engine unavailable")

            if task.get("status") == "completed":
                result_data = task.get("result") or {}
                break
            if task.get("status") == "failed":
                raise HTTPException(status_code=500, detail=task.get("error", "Agent task failed"))

        if result_data is None:
            raise HTTPException(status_code=504, detail="Agent task timed out")

    latency_ms = (time.time() - start_time) * 1000
    sources: List[SourceReference] = [
        SourceReference(
            doc_id=str(src.get("doc_id", "")),
            title=str(src.get("title", "")),
            score=float(src.get("score", 0.0)),
            excerpt=str(src.get("excerpt", "")),
            source_type=str(src.get("source_type", "")),
        )
        for src in (result_data.get("sources") or [])
    ]

    return QueryResponse(
        answer=result_data.get("output_text") or result_data.get("answer", ""),
        confidence=float(result_data.get("confidence", 0.0)),
        sources=sources,
        reasoning_steps=result_data.get("reasoning_steps", []),
        recommended_actions=result_data.get("recommended_actions", []),
        latency_ms=latency_ms,
    )
