from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware

from backend.services.api_gateway.src.config import get_settings
from backend.services.api_gateway.src.middleware.auth import JWTAuthMiddleware
from backend.services.api_gateway.src.middleware.rate_limiter import RateLimiterMiddleware
from backend.services.api_gateway.src.routers import agents, query, telemetry
from backend.services.api_gateway.src.websocket import realtime_handler
from backend.shared.infrastructure.tracing import instrument_fastapi, setup_otel_tracing, shutdown_tracing
from backend.shared.infrastructure.metrics import mount_metrics
from backend.shared.security.dev_auth import DevAuthMiddleware

logger = structlog.get_logger()

SERVICE_NAME = os.getenv("SERVICE_NAME", "api_gateway")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.1.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "false" if ENVIRONMENT == "development" else "true").lower() == "true"

_start_time = time.time()


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        trace_id = request.headers.get("X-Trace-Id", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        start = time.time()
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                latency_ms=round((time.time() - start) * 1000, 2),
                trace_id=trace_id,
            )
            return response
        except Exception as exc:
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                trace_id=trace_id,
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred.",
                    "request_id": trace_id,
                },
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_otel_tracing(
        service_name=SERVICE_NAME,
        otlp_endpoint=OTEL_ENDPOINT,
        environment=ENVIRONMENT,
        enable_console_export=(ENVIRONMENT == "development"),
    )
    settings = get_settings()
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=False)
    app.state.redis_client = redis_client
    logger.info("service_starting", service=SERVICE_NAME, version=SERVICE_VERSION, auth_enabled=AUTH_ENABLED)
    yield
    await redis_client.aclose()
    await shutdown_tracing()
    logger.info("service_stopped", service=SERVICE_NAME)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Industrial Knowledge Brain API Gateway",
        description="Production API Gateway for IKB v2.3.",
        version=SERVICE_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TracingMiddleware)

    if AUTH_ENABLED:
        app.add_middleware(JWTAuthMiddleware, settings=settings)
    else:
        app.add_middleware(DevAuthMiddleware)

    app.add_middleware(RateLimiterMiddleware)

    app.include_router(query.router)
    app.include_router(agents.router)
    app.include_router(telemetry.router)
    app.include_router(realtime_handler.router)

    instrument_fastapi(app)
    mount_metrics(app)
    return app


app = create_app()


@app.get("/health", tags=["system"])
async def health_check() -> dict:
    return {
        "status": "healthy",
        "version": SERVICE_VERSION,
        "uptime": round(time.time() - _start_time, 2),
        "service": SERVICE_NAME,
        "auth_enabled": AUTH_ENABLED,
    }


@app.get("/", tags=["system"])
async def root() -> dict:
    return {"service": SERVICE_NAME, "version": SERVICE_VERSION, "docs": "/docs"}
