"""
Admin Authentication
====================
Simple API key-based authentication for all admin endpoints.
"""

from __future__ import annotations

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

_api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=True)


async def require_admin(api_key: str = Security(_api_key_header)) -> None:
    """
    FastAPI dependency that validates the admin API key.
    Set ADMIN_API_KEY in .env. If empty, admin endpoints are unprotected (dev only).
    """
    from app.config import get_settings
    settings = get_settings()

    if not settings.admin_api_key:
        # In development without a key set, allow access but log a warning
        import logging
        logging.getLogger(__name__).warning(
            "ADMIN_API_KEY is not set – admin access is unprotected!"
        )
        return

    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key",
        )
