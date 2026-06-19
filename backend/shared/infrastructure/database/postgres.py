from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncGenerator, Optional

import asyncpg
from asyncpg.pool import Pool

logger = logging.getLogger(__name__)

# ── Module-level singleton pool ───────────────────────────────────────────────
# Initialised once per process during the FastAPI lifespan hook via
# init_db_pool(), closed via close_db_pool(), and injected via Depends(get_db_pool).
_pool_instance: Optional[asyncpg.Pool] = None


async def init_db_pool(
    dsn: Optional[str] = None,
    min_size: int = 5,
    max_size: int = 20,
) -> asyncpg.Pool:
    """
    Initialise the module-level PostgreSQL connection pool.
    Call once from the FastAPI lifespan hook:

        app.state.db_pool = await init_db_pool()
    """
    global _pool_instance
    if _pool_instance is not None:
        return _pool_instance

    resolved_dsn = dsn or os.environ.get(
        "DATABASE_URL",
        "postgresql://ikb_user:ikb_pass@postgres:5432/ikb_db",
    )
    _pool_instance = await asyncpg.create_pool(
        dsn=resolved_dsn,
        min_size=min_size,
        max_size=max_size,
    )
    logger.info("PostgreSQL pool initialised (min=%d, max=%d).", min_size, max_size)
    return _pool_instance


async def close_db_pool() -> None:
    """
    Gracefully close the module-level pool.
    Call from the FastAPI lifespan teardown section.
    """
    global _pool_instance
    if _pool_instance is not None:
        await _pool_instance.close()
        _pool_instance = None
        logger.info("PostgreSQL pool closed.")


async def get_db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """
    FastAPI dependency that yields the shared connection pool.

    Usage:
        @router.get("/foo")
        async def handler(pool: asyncpg.Pool = Depends(get_db_pool)):
            async with pool.acquire() as conn:
                ...
    """
    if _pool_instance is None:
        raise RuntimeError(
            "Database pool is not initialised. "
            "Call await init_db_pool() in the FastAPI lifespan hook."
        )
    yield _pool_instance


