"""
backend/shared/utils/logging.py

Centralised structured logging configuration using structlog.
Import and call configure_logging(SERVICE_NAME) at the top of each service's main.py.

Usage:
    from backend.shared.utils.logging import configure_logging, get_logger
    configure_logging("knowledge_engine")
    logger = get_logger(__name__)
    logger.info("event_name", key="value")
"""
from __future__ import annotations

import logging
import os
import sys

import structlog


def configure_logging(service_name: str) -> None:
    """
    Configure structlog for the given service.

    - Development (ENVIRONMENT=development): human-readable coloured output
    - Production / default: JSON lines — compatible with Grafana Loki / CloudWatch
    """
    environment = os.getenv("ENVIRONMENT", "production")
    level_name  = os.getenv("LOG_LEVEL", "DEBUG" if environment == "development" else "INFO")
    level       = getattr(logging, level_name.upper(), logging.INFO)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        # Inject service name into every log record
        lambda _, __, event_dict: {**event_dict, "service": service_name},
    ]

    if environment == "development":
        # Pretty, coloured output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON lines for production log aggregators
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging so third-party libraries (uvicorn, httpx)
    # produce structured output through the same pipeline
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=shared_processors + [renderer],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(name: str) -> structlog.BoundLogger:
    """Drop-in replacement for logging.getLogger(name)."""
    return structlog.get_logger(name)
