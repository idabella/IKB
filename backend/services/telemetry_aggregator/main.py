from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.shared.infrastructure.tracing import instrument_fastapi, setup_otel_tracing, shutdown_tracing
from backend.shared.infrastructure.metrics import mount_metrics
from backend.shared.infrastructure.database.postgres import init_db_pool, close_db_pool
from backend.shared.utils.logging import configure_logging
from backend.shared.security.dev_auth import DevAuthMiddleware
from backend.services.telemetry_aggregator.api.router import router as telemetry_router

# Configure structured logging before anything else
configure_logging(os.getenv("SERVICE_NAME", "telemetry_aggregator"))
logger = structlog.get_logger()

SERVICE_NAME    = os.getenv("SERVICE_NAME",    "telemetry_aggregator")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
ENVIRONMENT     = os.getenv("ENVIRONMENT",     "development")
OTEL_ENDPOINT   = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
CORS_ORIGINS    = os.getenv("CORS_ORIGINS",    "http://localhost:3000").split(",")
DATABASE_URL    = os.getenv("DATABASE_URL",    "postgresql://ikb_user:ikb_pass@postgres:5432/ikb_db")
REDIS_URL       = os.getenv("REDIS_URL",       "redis://:ikb_redis_2024@redis:6379/1")
KAFKA_SERVERS   = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")

_start_time = time.time()
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false" if ENVIRONMENT == "development" else "true").lower() == "true"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_otel_tracing(service_name=SERVICE_NAME, otlp_endpoint=OTEL_ENDPOINT, environment=ENVIRONMENT)
    logger.info("service_starting", service=SERVICE_NAME, version=SERVICE_VERSION)

    # ── PostgreSQL pool ───────────────────────────────────────────────────────
    app.state.db_pool = await init_db_pool(dsn=DATABASE_URL, min_size=3, max_size=10)
    logger.info("db_pool_ready")

    # ── Redis client + TelemetryRedisCache ─────────────────────────────────────
    from redis.asyncio import Redis as AsyncRedis
    from backend.services.telemetry_aggregator.application.cache.redis_cache import TelemetryRedisCache

    redis_client = AsyncRedis.from_url(REDIS_URL, decode_responses=False)
    redis_cache  = TelemetryRedisCache(client=redis_client)
    app.state.redis_client = redis_client   # for graceful shutdown
    app.state.redis_cache  = redis_cache    # accessible in routers if needed
    logger.info("redis_cache_ready", url=REDIS_URL)

    # ── Telemetry Stream Processor ───────────────────────────────────────────
    from backend.services.telemetry_aggregator.application.stream_processor import TelemetryStreamProcessor
    processor = TelemetryStreamProcessor(
        db_pool=app.state.db_pool,
        redis_cache=redis_cache,
        kafka_bootstrap_servers=KAFKA_SERVERS,
    )
    app.state.stream_processor = processor   # expose for routers via request.app.state
    await processor.start()
    logger.info("kafka_consumer_started", servers=KAFKA_SERVERS)

    yield

    # ── Teardown (reverse order) ────────────────────────────────────────────
    await processor.stop()
    logger.info("kafka_consumer_stopped")
    await redis_client.aclose()
    logger.info("redis_closed")
    await close_db_pool()
    await shutdown_tracing()
    logger.info("service_stopped", service=SERVICE_NAME)


app = FastAPI(
    title=f"IKB — {SERVICE_NAME}",
    description=(
        "Telemetry Aggregator: consolidates sensor ingestion, anomaly detection "
        "(rule / statistical / ML), and time-series persistence. "
        "Replaces the old standalone telemetry_service."
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

app.include_router(telemetry_router, prefix="/api/v1")


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
        "uptime": round(time.time() - _start_time, 2),
        "capabilities": ["sensor_ingest", "anomaly_detection", "time_series"],
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION, "docs": "/docs"}
