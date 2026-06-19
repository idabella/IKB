from __future__ import annotations

import uuid
from typing import Any, Dict

import asyncpg
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from backend.services.knowledge_engine.api.dependencies import get_ingest_handler, get_db
from backend.shared.security.rbac import require_roles, Roles

logger = structlog.get_logger(__name__)

router = APIRouter()


def _extract_text(raw_bytes: bytes, filename: str, doc_type: str) -> str:
    lower_name = filename.lower()
    if lower_name.endswith(".pdf"):
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(raw_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return raw_bytes.decode("utf-8", errors="replace")


class IngestResponse(BaseModel):
    job_id: str
    status: str
    filename: str


@router.post("/document", response_model=IngestResponse, status_code=202)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tenant_id: str = Form(...),
    factory_id: str = Form("default"),
    doc_type: str = Form("manual"),
    ingest_handler=Depends(get_ingest_handler),
    db_pool: asyncpg.Pool = Depends(get_db),
    _rbac=Depends(require_roles([Roles.ENGINEER, Roles.ADMIN])),
) -> IngestResponse:
    """
    Upload and ingest a document (PDF, TXT, DOCX).

    Chunking → embedding → Qdrant upsert runs as a background task
    using the singleton IngestDocumentHandler from app.state.

    Pipeline:  Upload → BackgroundTask → IngestDocumentHandler → Qdrant
    (Before):  API Gateway → Ingestion Service → Kafka → RAG Service → Qdrant
    """
    job_id    = str(uuid.uuid4())
    filename  = file.filename or "unknown"
    raw_bytes = await file.read()

    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ingestion_jobs
                (id, source_type, status, source_url, tenant_id, factory_id, created_at, updated_at)
            VALUES ($1, 'upload', 'processing', $2, $3, $4, NOW(), NOW())
            """,
            job_id, filename, tenant_id, factory_id,
        )

    async def _process(handler, pool, jid: str, data: bytes, meta: Dict[str, Any]) -> None:
        try:
            from backend.services.knowledge_engine.rag_application.commands.ingest_document import IngestDocumentCommand

            text = _extract_text(data, meta.get("filename", ""), meta.get("doc_type", "manual"))
            cmd = IngestDocumentCommand(
                doc_id=jid,
                tenant_id=meta["tenant_id"],
                text=text,
                source_type=meta.get("doc_type", "manual"),
                metadata=meta,
                chunking_strategy="parent_child",
            )
            await handler.handle(cmd)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE ingestion_jobs SET status='done', updated_at=NOW() WHERE id=$1", jid
                )
            logger.info("ingestion_job_completed", job_id=jid, filename=meta.get("filename"))
        except Exception as exc:
            logger.error("ingestion_job_failed", job_id=jid, error=str(exc), exc_info=True)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE ingestion_jobs SET status='failed', updated_at=NOW() WHERE id=$1", jid
                )

    background_tasks.add_task(
        _process,
        ingest_handler,
        db_pool,
        job_id,
        raw_bytes,
        {"tenant_id": tenant_id, "factory_id": factory_id, "doc_type": doc_type, "filename": filename},
    )
    logger.info("ingestion_job_accepted", job_id=job_id, filename=filename, tenant_id=tenant_id)
    return IngestResponse(job_id=job_id, status="processing", filename=filename)


@router.get("/jobs/{job_id}")
async def get_ingestion_job(
    job_id: str,
    db_pool: asyncpg.Pool = Depends(get_db),
    _rbac=Depends(require_roles([Roles.OPERATOR, Roles.ENGINEER, Roles.ADMIN])),
) -> Dict[str, Any]:
    """Poll the status of a document ingestion job."""
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, source_url, source_type, tenant_id, factory_id, created_at, updated_at "
            "FROM ingestion_jobs WHERE id=$1",
            job_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Ingestion job not found")
    return dict(row)
