"""
backend/shared/security/rbac.py

Role-based access control helpers shared across services.
Use require_roles() as a FastAPI dependency on protected routes.

Usage:
    from backend.shared.security.rbac import require_roles

    @router.post("/ingest/document")
    async def ingest(req: ..., _=Depends(require_roles(["engineer", "admin"]))):
        ...
"""
from __future__ import annotations

import os
from typing import List

from fastapi import Depends, HTTPException, Request

RBAC_ENABLED = os.getenv("RBAC_ENABLED", "false" if os.getenv("ENVIRONMENT", "development") == "development" else "true").lower() == "true"


# Canonical role names — match the Keycloak realm/resource roles in JWT
class Roles:
    OPERATOR  = "operator"
    ENGINEER  = "engineer"
    ADMIN     = "admin"
    API_CLIENT = "api_client"
    READONLY  = "readonly"


def get_current_roles(request: Request) -> List[str]:
    """
    Extract roles injected by JWTAuthMiddleware from request.state.
    Returns an empty list if middleware hasn't run (e.g. /health path).
    """
    return getattr(request.state, "roles", [])


def require_roles(allowed_roles: List[str]):
    """
    FastAPI dependency factory.  Raises 403 if the authenticated user
    has none of the allowed roles.

    Example:
        @router.post("/sensitive")
        async def endpoint(_=Depends(require_roles([Roles.ENGINEER, Roles.ADMIN]))):
            ...
    """
    def _check(roles: List[str] = Depends(get_current_roles)) -> None:
        if not RBAC_ENABLED:
            return
        if not any(r in allowed_roles for r in roles):
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "FORBIDDEN",
                    "message": f"Required one of: {allowed_roles}",
                },
            )
    return _check


def require_any_role(request: Request) -> None:
    """Dependency that just ensures the user is authenticated with at least one role."""
    roles = getattr(request.state, "roles", [])
    if not roles:
        raise HTTPException(
            status_code=403,
            detail={"error_code": "FORBIDDEN", "message": "No roles assigned to token"},
        )
