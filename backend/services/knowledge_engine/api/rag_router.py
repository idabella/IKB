from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from backend.services.knowledge_engine.api.dependencies import get_retrieve_handler, get_db
from backend.shared.security.rbac import require_roles, Roles

logger = structlog.get_logger(__name__)

router = APIRouter()

# Redis cache TTL for RAG results (10 minutes)
_CACHE_TTL = 600


class RetrieveRequest(BaseModel):
    query: str
    tenant_id: str
    machine_ids: Optional[List[str]] = None
    doc_types: Optional[List[str]] = None
    top_k: int = 5


class RetrieveResponse(BaseModel):
    chunks: List[Dict[str, Any]]
    total: int
    query: str
    cached: bool = False


def _cache_key(req: RetrieveRequest) -> str:
    """Deterministic cache key scoped to tenant + query + filters."""
    raw = f"{req.tenant_id}:{req.query}:{req.machine_ids}:{req.doc_types}:{req.top_k}"
    return f"rag:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve_context(
    req: RetrieveRequest,
    request: Request,
    retrieve_handler=Depends(get_retrieve_handler),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
) -> RetrieveResponse:
    """
    In-process semantic knowledge retrieval.

    Uses the singleton RetrieveContextHandler built at startup (app.state),
    which queries Qdrant directly — no HTTP round-trip.

    Before: Agent → HTTP → RAG Service → Qdrant
    After:  Knowledge Engine (in-process) → Qdrant

    Results are cached in Redis for 10 minutes per (tenant_id + query).
    """
    # ── L1 Redis cache ────────────────────────────────────────────────────────
    redis_client = getattr(request.app.state, "redis_client", None)
    cache_key = _cache_key(req)

    if redis_client:
        cached = await redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            logger.debug("rag_cache_hit", key=cache_key[:16])
            return RetrieveResponse(**data, cached=True)

    # ── Live retrieval ────────────────────────────────────────────────────────
    try:
        from backend.services.knowledge_engine.rag_application.queries.retrieve_context import RetrieveContextQuery
        context_query = RetrieveContextQuery(
            query=req.query,
            tenant_id=req.tenant_id,
            machine_ids=req.machine_ids or [],
            doc_types=req.doc_types or [],
            top_k=req.top_k,
        )
        results = await retrieve_handler.handle(context_query)
        chunks = [
            {
                "text": r.text,
                "score": r.score,
                "doc_id": r.source_doc,
                "metadata": r.metadata,
            }
            for r in results
        ]
        response = RetrieveResponse(chunks=chunks, total=len(chunks), query=req.query)

        # ── Store in cache ────────────────────────────────────────────────────
        if redis_client:
            await redis_client.setex(cache_key, _CACHE_TTL, response.model_dump_json())

        logger.info("rag_retrieval_completed", query_len=len(req.query), chunks=len(chunks))
        return response

    except Exception as exc:
        logger.error("rag_retrieval_failed", query=req.query[:60], error=str(exc), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {exc}")
