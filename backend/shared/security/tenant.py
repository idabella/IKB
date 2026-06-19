"""
backend/shared/security/tenant.py

Tenant context extraction and validation.
Works alongside JWTAuthMiddleware which injects tenant_id into request.state.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request


def get_tenant_id(request: Request) -> str:
    """
    FastAPI dependency — extracts the tenant_id injected by JWTAuthMiddleware.
    Raises 401 if tenant_id is missing (guard against misconfigured tokens).
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=401,
            detail={
                "error_code": "MISSING_TENANT",
                "message": "Token is missing required tenant_id claim",
            },
        )
    return tenant_id


def require_tenant(tenant_id: str = Depends(get_tenant_id)) -> str:
    """Alias for get_tenant_id — explicit naming for routes that require tenant isolation."""
    return tenant_id
