from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

import asyncpg
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.services.knowledge_engine.api.dependencies import get_orchestrator, get_db
from backend.shared.security.rbac import require_roles, Roles

logger = structlog.get_logger(__name__)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    session_id: str
    tenant_id: str
    task_id: Optional[str] = None
    query: str
    task_type: str = "conversational_query"
    metadata: Dict[str, Any] = {}


@router.post("/analyze")
async def submit_analysis_task(
    req: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    orchestrator=Depends(get_orchestrator),
    db_pool: asyncpg.Pool = Depends(get_db),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
) -> Dict[str, str]:
    """
    Submit an async agent analysis task.

    The agent orchestrator (injected from app.state) uses in-process tool calls —
    no additional HTTP hops inside the ReAct reasoning loop.
    Returns immediately with a task_id; poll /tasks/{id} or stream /tasks/{id}/stream.
    """
    from backend.services.knowledge_engine.domain.models.agent_task import AgentTask

    task_id = req.task_id or str(uuid.uuid4())
    agent_task = AgentTask(
        session_id=req.session_id,
        tenant_id=req.tenant_id,
        task_id=task_id,
        query=req.query,
        metadata={**req.metadata, "task_type": req.task_type},
    )

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks
                (task_id, session_id, tenant_id, status, query, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, 'processing', $4, $5::jsonb, NOW(), NOW())
            """,
            task_id, req.session_id, req.tenant_id, req.query,
            json.dumps(agent_task.metadata),
        )

    async def _run(task, orch, pool):
        try:
            result = await orch.route_and_execute(task)
            payload = result.model_dump() if hasattr(result, "model_dump") else result
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE agent_tasks SET status='completed', result=$1::jsonb, updated_at=NOW() WHERE task_id=$2",
                    json.dumps(payload), task.task_id,
                )
            logger.info("agent_task_completed", task_id=task.task_id)
        except Exception as exc:
            logger.error("agent_task_failed", task_id=task.task_id, error=str(exc), exc_info=True)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE agent_tasks SET status='failed', error=$1, updated_at=NOW() WHERE task_id=$2",
                    str(exc), task.task_id,
                )

    background_tasks.add_task(_run, agent_task, orchestrator, db_pool)
    return {"task_id": task_id, "status": "processing"}


@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    db_pool: asyncpg.Pool = Depends(get_db),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
) -> Dict[str, Any]:
    """Poll task status and result."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT task_id, session_id, tenant_id, status, query,
                   metadata, result, error, created_at, updated_at
            FROM agent_tasks WHERE task_id = $1
            """,
            task_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return dict(row)


@router.get("/tasks/{task_id}/stream")
async def stream_task_result(
    task_id: str,
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
):
    """
    Stream agent reasoning steps via Server-Sent Events.

    Eliminates the need for clients to poll /tasks/{id} repeatedly.
    Each SSE event is a JSON-encoded reasoning step emitted by the
    AgentOrchestrator as it executes tools in the ReAct loop.

    Connect with: EventSource('/api/v1/agents/tasks/{id}/stream')
    """
    # Verify task exists before opening the stream
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT task_id, status FROM agent_tasks WHERE task_id = $1", task_id
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Task not found")

    orchestrator = request.app.state.orchestrator

    async def event_generator():
        try:
            if hasattr(orchestrator, "stream") and callable(orchestrator.stream):
                # Stream live steps if orchestrator supports it
                async for step in orchestrator.stream(task_id):
                    data = step.model_dump_json() if hasattr(step, "model_dump_json") else json.dumps(step)
                    yield f"data: {data}\n\n"
            else:
                # Fallback: poll DB until complete and emit status events
                import asyncio
                for _ in range(120):  # max 2 min (1s polls)
                    await asyncio.sleep(1)
                    async with db_pool.acquire() as conn:
                        row = await conn.fetchrow(
                            "SELECT status, result, error FROM agent_tasks WHERE task_id = $1",
                            task_id,
                        )
                    if row and row["status"] in ("completed", "failed"):
                        yield f"data: {json.dumps(dict(row))}\n\n"
                        break
                    yield f"data: {json.dumps({'status': row['status'] if row else 'unknown'})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering for SSE
        },
    )


@router.get("/tasks/{task_id}/trace")
async def get_task_trace(
    task_id: str,
    db_pool: asyncpg.Pool = Depends(get_db),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
) -> Dict[str, Any]:
    """Retrieve per-step tool execution trace for a task."""
    async with db_pool.acquire() as conn:
        exists = await conn.fetchrow("SELECT task_id FROM agent_tasks WHERE task_id=$1", task_id)
        if exists is None:
            raise HTTPException(status_code=404, detail="Task not found")
        rows = await conn.fetch(
            """
            SELECT tool_name, input_params, output_data, success,
                   error_message, duration_ms, created_at
            FROM agent_tool_calls
            WHERE task_id = $1 ORDER BY created_at ASC
            """,
            task_id,
        )
    return {"task_id": task_id, "trace": [dict(r) for r in rows]}


@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    db_pool: asyncpg.Pool = Depends(get_db),
    _rbac=Depends(require_roles([Roles.ENGINEER, Roles.ADMIN])),
) -> Dict[str, str]:
    """Mark a running task as cancelled."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT task_id, status FROM agent_tasks WHERE task_id=$1",
            task_id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if row["status"] in ("completed", "failed", "cancelled"):
            return {"task_id": task_id, "status": row["status"]}
        await conn.execute(
            "UPDATE agent_tasks SET status='cancelled', updated_at=NOW() WHERE task_id=$1",
            task_id,
        )
    return {"task_id": task_id, "status": "cancelled"}
