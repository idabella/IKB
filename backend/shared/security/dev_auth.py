"""
Optional development auth middleware.

When AUTH_ENABLED=false, injects tenant_id and roles so RBAC-protected routes
work without Keycloak during local development and integration tests.
"""
from __future__ import annotations

import os
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

_SKIP_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/metrics"}


class DevAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in _SKIP_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        if not request.state.__dict__.get("tenant_id"):
            request.state.tenant_id = request.headers.get(
                "X-Tenant-ID",
                os.getenv("DEFAULT_TENANT_ID", "default"),
            )
        if not getattr(request.state, "roles", None):
            request.state.roles = ["admin", "engineer", "operator", "api_client"]
        if not getattr(request.state, "user_id", None):
            request.state.user_id = "dev-user"

        return await call_next(request)
