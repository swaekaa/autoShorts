"""
Admin Settings and Controls API
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.database import get_async_session
from app.models import QuotaEvent, ServiceSettings
from app.quota_manager import QuotaManager
from app.schemas import QuotaEventRead, ServiceSettingsRead, ServiceSettingsUpdate

router = APIRouter(prefix="/admin", tags=["Admin - Settings"])


async def _get_or_create_settings(session: AsyncSession) -> ServiceSettings:
    result = await session.execute(select(ServiceSettings).where(ServiceSettings.id == 1))
    svc = result.scalar_one_or_none()
    if not svc:
        svc = ServiceSettings(id=1)
        session.add(svc)
        await session.flush()
    return svc


@router.get("/settings", response_model=ServiceSettingsRead)
async def get_settings(
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    return await _get_or_create_settings(session)


@router.patch("/settings", response_model=ServiceSettingsRead)
async def update_settings(
    updates: ServiceSettingsUpdate,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    svc = await _get_or_create_settings(session)
    for field, value in updates.model_dump(exclude_none=True).items():
        setattr(svc, field, value)
    await session.commit()
    return svc


@router.post("/emergency-stop")
async def emergency_stop(
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    """Immediately halt all generation and publishing."""
    svc = await _get_or_create_settings(session)
    svc.emergency_stop = True
    await session.commit()
    return {"message": "Emergency stop activated"}


@router.post("/resume")
async def resume_service(
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    """Clear emergency stop and re-enable the service."""
    svc = await _get_or_create_settings(session)
    svc.emergency_stop = False
    svc.enabled = True
    await session.commit()
    return {"message": "Service resumed"}


@router.get("/quota-events", response_model=list[QuotaEventRead])
async def list_quota_events(
    limit: int = 50,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    """View recent quota events for debugging."""
    from sqlalchemy import desc
    result = await session.execute(
        select(QuotaEvent)
        .order_by(desc(QuotaEvent.event_timestamp))
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/quota-states")
async def get_quota_states(
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    """View current quota state for all providers."""
    from app.config import get_settings
    settings = get_settings()
    qm = QuotaManager(session, settings)
    return await qm.get_all_states()
