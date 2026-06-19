from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from urllib.parse import urlparse

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.shared.infrastructure.tracing import instrument_fastapi, setup_otel_tracing, shutdown_tracing
from backend.shared.infrastructure.metrics import mount_metrics
from backend.shared.infrastructure.database.postgres import init_db_pool, close_db_pool
from backend.shared.utils.logging import configure_logging
from backend.shared.security.dev_auth import DevAuthMiddleware
from backend.services.knowledge_engine.api.router import router as engine_router

# Configure structured logging before any logger is created
configure_logging(os.getenv("SERVICE_NAME", "knowledge_engine"))
logger = structlog.get_logger()

# ── Configuration (read once at import time) ────────────────────────────────
SERVICE_NAME    = os.getenv("SERVICE_NAME", "knowledge_engine")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
ENVIRONMENT     = os.getenv("ENVIRONMENT", "development")
OTEL_ENDPOINT   = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
CORS_ORIGINS    = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
DATABASE_URL    = os.getenv("DATABASE_URL", "postgresql://ikb_user:ikb_pass@postgres:5432/ikb_db")
REDIS_URL       = os.getenv("REDIS_URL", "redis://:ikb_redis_2024@redis:6379/0")
QDRANT_URL      = os.getenv("QDRANT_URL", "http://qdrant:6333")
NEO4J_URI       = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER      = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD  = os.getenv("NEO4J_PASSWORD", "neo4j")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
GEMINI_EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
GEMINI_EMBEDDING_DIM   = int(os.getenv("GEMINI_EMBEDDING_DIM", "768"))
KAFKA_SERVERS   = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
TENANT_DEFAULT  = os.getenv("DEFAULT_TENANT_ID", "default")

_start_time = time.time()
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false" if ENVIRONMENT == "development" else "true").lower() == "true"


def _qdrant_host_port() -> tuple[str, int]:
    parsed = urlparse(QDRANT_URL)
    host = parsed.hostname or "qdrant"
    port = parsed.port or 6333
    return host, port


# ── Dependency factory helpers ───────────────────────────────────────────────

def _build_retrieve_handler(redis_client):
    """
    Construct a RetrieveContextHandler wired to production infrastructure.
    Called ONCE during lifespan; stored in app.state.retrieve_handler.

    Args:
        redis_client: Shared redis.asyncio.Redis instance (for ParentRetriever cache).
    """
    from backend.services.knowledge_engine.llm.gemini_client import GeminiClient
    from backend.services.knowledge_engine.rag.embedders.gemini_embedder import GeminiEmbedder
    from backend.services.knowledge_engine.rag.vector_stores.qdrant_store import QdrantStore
    from backend.services.knowledge_engine.rag.retrievers.hybrid_retriever import HybridRetriever
    from backend.services.knowledge_engine.rag.retrievers.multi_query_retriever import MultiQueryRetriever
    from backend.services.knowledge_engine.rag.retrievers.parent_retriever import ParentRetriever
    from backend.services.knowledge_engine.rag.rerankers.cross_encoder_reranker import CrossEncoderReranker
    from backend.services.knowledge_engine.rag_application.queries.retrieve_context import RetrieveContextHandler

    host, port = _qdrant_host_port()
    vector_store = QdrantStore(host=host, port=port, dense_dim=GEMINI_EMBEDDING_DIM)
    embedder     = GeminiEmbedder(api_key=GEMINI_API_KEY, model_name=GEMINI_EMBEDDING_MODEL, output_dimensionality=GEMINI_EMBEDDING_DIM)
    llm_client   = GeminiClient(api_key=GEMINI_API_KEY)
    hybrid       = HybridRetriever(vector_store=vector_store, embedder=embedder)
    multi_query  = MultiQueryRetriever(hybrid_retriever=hybrid, llm_client=llm_client)
    parent       = ParentRetriever(redis_client=redis_client)
    reranker     = CrossEncoderReranker()

    return RetrieveContextHandler(
        multi_query_retriever=multi_query,
        parent_retriever=parent,
        reranker=reranker,
    )


def _build_ingest_handler(redis_client, kafka_producer, db_pool):
    """
    Construct an IngestDocumentHandler wired to production infrastructure.
    Called ONCE during lifespan; stored in app.state.ingest_handler.
    """
    from qdrant_client import AsyncQdrantClient

    from backend.services.knowledge_engine.rag.embedders.gemini_embedder import GeminiEmbedder
    from backend.services.knowledge_engine.rag_application.commands.ingest_document import IngestDocumentHandler

    host, port = _qdrant_host_port()
    qdrant_client = AsyncQdrantClient(host=host, port=port)
    embedder = GeminiEmbedder(api_key=GEMINI_API_KEY, model_name=GEMINI_EMBEDDING_MODEL, output_dimensionality=GEMINI_EMBEDDING_DIM)

    async def embedding_function(text: str):
        return await embedder.embed_document(text)

    return IngestDocumentHandler(
        qdrant_client=qdrant_client,
        redis_client=redis_client,
        kafka_producer=kafka_producer,
        db_pool=db_pool,
        embedding_function=embedding_function,
    )


def _build_orchestrator(retrieve_handler, redis_client, kafka_producer):
    """
    Construct an AgentOrchestrator with all agents wired to in-process tools.
    Called ONCE during lifespan; stored in app.state.orchestrator.

    Args:
        retrieve_handler: Singleton RetrieveContextHandler.
        redis_client:     Shared redis.asyncio.Redis instance (for EpisodicMemory).
        kafka_producer:   Singleton KafkaMessageProducer (for MonitoringAgent escalation).
    """
    from backend.services.knowledge_engine.llm.gemini_client import GeminiClient
    from backend.services.knowledge_engine.memory.episodic_memory import EpisodicMemory
    from backend.services.knowledge_engine.tools.rag_tool import RagTool
    from backend.services.knowledge_engine.agents.root_cause_agent import RootCauseAgent
    from backend.services.knowledge_engine.agents.maintenance_agent import MaintenanceAgent
    from backend.services.knowledge_engine.agents.monitoring_agent import MonitoringAgent
    from backend.services.knowledge_engine.application.orchestrator import AgentOrchestrator

    llm_client   = GeminiClient(api_key=GEMINI_API_KEY)
    # fixed: EpisodicMemory now receives the shared Redis client
    memory_store = EpisodicMemory(redis_client=redis_client, llm_client=llm_client)

    # RagTool wired to in-process handler — no HTTP round-trip
    rag_tool = RagTool(retrieve_handler=retrieve_handler, tenant_id=TENANT_DEFAULT)
    tool_registry = {"rag_search": rag_tool}

    rca_agent         = RootCauseAgent(llm_client=llm_client, tool_registry=tool_registry, memory_store=memory_store)
    maintenance_agent = MaintenanceAgent(llm_client=llm_client, tool_registry=tool_registry, memory_store=memory_store)
    # fixed: MonitoringAgent receives singleton producer — no per-call reconnect
    monitoring_agent  = MonitoringAgent(
        llm_client=llm_client,
        tool_registry=tool_registry,
        memory_store=memory_store,
        kafka_producer=kafka_producer,
    )

    return AgentOrchestrator(
        rca_agent=rca_agent,
        maintenance_agent=maintenance_agent,
        monitoring_agent=monitoring_agent,
    )


# ── Internal endpoint: receives escalations from Telemetry Aggregator ──────────────
# Replaces the ikb.agent.tasks Kafka topic — same business logic, simpler wiring.
# Only reachable from within the docker network (no auth required at transport level;
# the TA is a trusted internal caller).

async def _handle_internal_agent_task(app: FastAPI, task_data: dict) -> None:
    """
    Process an anomaly escalation task submitted by the Telemetry Aggregator.
    Replaces the old ikb.agent.tasks Kafka consumer — same business logic, simpler wiring.
    """
    from backend.services.knowledge_engine.domain.models.agent_task import AgentTask

    machine_id = task_data.get("machine_id", "unknown")
    sensor_id  = task_data.get("sensor_id", "unknown")
    severity   = task_data.get("severity", "UNKNOWN")

    query = (
        f"Perform root cause analysis for machine {machine_id}. "
        f"Anomaly detected: sensor={sensor_id}, severity={severity}, "
        f"value={task_data.get('trigger_value', 'N/A')}."
    )
    agent_task = AgentTask(
        task_id=task_data.get("anomaly_id") or str(uuid.uuid4()),
        session_id=f"internal-escalation-{machine_id}",
        tenant_id=TENANT_DEFAULT,
        query=query,
        metadata=task_data,
    )

    db_pool = app.state.db_pool
    async with db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO agent_tasks
                (task_id, session_id, tenant_id, status, query, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, 'processing', $4, $5::jsonb, NOW(), NOW())
            ON CONFLICT (task_id) DO NOTHING
            """,
            agent_task.task_id,
            agent_task.session_id,
            agent_task.tenant_id,
            agent_task.query,
            json.dumps(agent_task.metadata),
        )

    orchestrator = app.state.orchestrator
    result = await orchestrator.route_and_execute(agent_task)
    result_payload = result.model_dump() if hasattr(result, "model_dump") else result

    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE agent_tasks SET status='completed', result=$1::jsonb, updated_at=NOW() WHERE task_id=$2",
            json.dumps(result_payload),
            agent_task.task_id,
        )
    logger.info("internal_agent_task_completed", task_id=agent_task.task_id, machine_id=machine_id)


# ── FastAPI Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan: build ALL singletons once and store in app.state.
    Construction order mirrors dependency graph:
      1. DB pool  →  2. Redis  →  3. Kafka producer  →  4. RAG pipeline  →  5. Orchestrator
    """
    setup_otel_tracing(service_name=SERVICE_NAME, otlp_endpoint=OTEL_ENDPOINT, environment=ENVIRONMENT)
    logger.info("service_starting", service=SERVICE_NAME, version=SERVICE_VERSION)

    # ── 1. PostgreSQL pool ────────────────────────────────────────────────────
    logger.info("initialising_db_pool")
    db_pool = await init_db_pool(dsn=DATABASE_URL, min_size=5, max_size=20)
    app.state.db_pool = db_pool

    # ── 2. Redis client ───────────────────────────────────────────────────────
    # Shared by: RAG L1 cache (rag_router), ParentRetriever, EpisodicMemory
    logger.info("initialising_redis_client")
    from redis.asyncio import Redis as AsyncRedis
    redis_client = AsyncRedis.from_url(REDIS_URL, decode_responses=False)
    app.state.redis_client = redis_client

    # ── 3. Kafka producer (singleton) ─────────────────────────────────────────
    # Injected into MonitoringAgent — avoids per-call connect/disconnect overhead
    logger.info("initialising_kafka_producer")
    from backend.shared.infrastructure.messaging.kafka_producer import KafkaMessageProducer
    kafka_producer = KafkaMessageProducer()
    await kafka_producer.start()
    app.state.kafka_producer = kafka_producer

    # ── 4. RAG pipeline ───────────────────────────────────────────────────────
    logger.info("initialising_rag_pipeline")
    retrieve_handler = _build_retrieve_handler(redis_client=redis_client)
    app.state.retrieve_handler = retrieve_handler

    ingest_handler = _build_ingest_handler(
        redis_client=redis_client,
        kafka_producer=kafka_producer,
        db_pool=db_pool,
    )
    app.state.ingest_handler = ingest_handler

    # ── 5. Agent orchestrator ─────────────────────────────────────────────────
    logger.info("initialising_agent_orchestrator")
    orchestrator = _build_orchestrator(
        retrieve_handler=retrieve_handler,
        redis_client=redis_client,
        kafka_producer=kafka_producer,
    )
    app.state.orchestrator = orchestrator

    # ── 6. Internal escalation endpoint (registered on the app, not via router) ─
    # Receives HTTP POST from Telemetry Aggregator (replaces ikb.agent.tasks Kafka topic)
    @app.post("/api/v1/internal/agent-tasks", include_in_schema=False)
    async def _internal_agent_task(request):
        from fastapi.responses import JSONResponse
        body = await request.json()
        asyncio.create_task(_handle_internal_agent_task(app, body))
        return JSONResponse({"status": "accepted"}, status_code=202)

    logger.info("service_ready", service=SERVICE_NAME, version=SERVICE_VERSION)
    yield

    # ── Teardown (reverse order) ───────────────────────────────────────────────
    logger.info("service_shutting_down", service=SERVICE_NAME)
    await kafka_producer.stop()
    await redis_client.aclose()
    await close_db_pool()
    await shutdown_tracing()
    logger.info("service_stopped", service=SERVICE_NAME)


# ── Application ──────────────────────────────────────────────────────────────

app = FastAPI(
    title=f"IKB — {SERVICE_NAME}",
    description=(
        "Unified Knowledge Engine: consolidates Agent orchestration, "
        "RAG retrieval, and Knowledge Graph operations into a single "
        "deployable unit. Eliminates inter-service HTTP overhead.\n\n"
        "All dependencies (RetrieveContextHandler, AgentOrchestrator, "
        "IngestDocumentHandler) are constructed once at startup and stored "
        "in app.state, making them truly singleton per process."
    ),
    version=SERVICE_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not AUTH_ENABLED:
    app.add_middleware(DevAuthMiddleware)

instrument_fastapi(app)
mount_metrics(app)
app.include_router(engine_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "uptime": round(time.time() - _start_time, 2),
        "capabilities": ["agents", "rag", "graph", "ingestion"],
        "singletons_ready": {
            "db_pool":          hasattr(app.state, "db_pool"),
            "retrieve_handler": hasattr(app.state, "retrieve_handler"),
            "ingest_handler":   hasattr(app.state, "ingest_handler"),
            "orchestrator":     hasattr(app.state, "orchestrator"),
        },
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION, "docs": "/docs"}
