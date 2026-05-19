import logging
import time
import uuid
from typing import Callable, Any
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter using Redis sorted sets.
    Implements per-tenant limits and fails open on cache issues.
    """
    
    def __init__(self, app: Any, redis_client: Redis) -> None:
        super().__init__(app)
        self.redis = redis_client
        self.default_limit = 100
        self.agent_limit = 10
        self.skip_paths = {"/health", "/api/docs", "/api/openapi.json", "/openapi.json", "/metrics"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in self.skip_paths or request.method == "OPTIONS":
            return await call_next(request)

        tenant_id = getattr(request.state, "tenant_id", "anonymous")
        
        limit = self.agent_limit if request.url.path.startswith("/api/v1/agents") else self.default_limit
        
        allowed = True
        current_time = time.time()
        window = 60
        key = f"rate_limit:{tenant_id}:{request.url.path}"
        
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, 0, current_time - window)
                pipe.zcard(key)
                
                # Append a UUID to ensure uniqueness against rapid parallel requests
                member = f"{current_time}-{uuid.uuid4()}"
                pipe.zadd(key, mapping={member: current_time})
                pipe.expire(key, window)
                
                results = await pipe.execute()
                
            request_count = results[1]
            allowed = request_count < limit
        except Exception as e:
            logger.error("Redis rate limiter failed for tenant %s: %s", tenant_id, str(e))
            allowed = True # Fail open so valid traffic isn't blocked by infrastructure issues
        
        if not allowed:
            logger.warning("Rate limit exceeded for tenant %s on %s", tenant_id, request.url.path)
            response = JSONResponse(
                status_code=429,
                content={
                    "error_code": "RATE_LIMITED",
                    "message": f"Rate limit of {limit} req/min exceeded.",
                    "request_id": getattr(request.state, "trace_id", "N/A"),
                    "timestamp": current_time
                }
            )
            response.headers["Retry-After"] = "60"
            return response

        return await call_next(request)
