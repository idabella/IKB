from __future__ import annotations

from fastapi import APIRouter

from backend.services.knowledge_engine.api.agents_router import router as agents_router
from backend.services.knowledge_engine.api.rag_router import router as rag_router
from backend.services.knowledge_engine.api.ingest_router import router as ingest_router

# Top-level router that aggregates all engine sub-domains
router = APIRouter()

router.include_router(agents_router, prefix="/agents", tags=["Agents"])
router.include_router(rag_router, prefix="/rag", tags=["RAG"])
router.include_router(ingest_router, prefix="/ingest", tags=["Ingestion"])
