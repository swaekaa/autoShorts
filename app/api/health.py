"""
Health Check Endpoint
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.schemas import HealthResponse

router = APIRouter()
_WORKER_RUNNING = False
_VERSION = "1.0.0"


def set_worker_running(state: bool) -> None:
    global _WORKER_RUNNING
    _WORKER_RUNNING = state


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(session: AsyncSession = Depends(get_async_session)):
    """Returns service health status."""
    # Test DB connectivity
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # Get runtime stats
    daily_videos = 0
    daily_spend = 0.0
    emergency_stop = False

    try:
        from sqlalchemy import func, select
        from app.models import VideoJob, JobStatus, QuotaEvent, ServiceSettings
        from datetime import datetime, timezone

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        count_result = await session.execute(
            select(func.count(VideoJob.id)).where(
                VideoJob.status == JobStatus.COMPLETED,
                VideoJob.completed_at >= today_start,
            )
        )
        daily_videos = int(count_result.scalar_one() or 0)

        spend_result = await session.execute(
            select(func.coalesce(func.sum(QuotaEvent.estimated_cost_usd), 0.0)).where(
                QuotaEvent.event_timestamp >= today_start
            )
        )
        daily_spend = float(spend_result.scalar_one() or 0.0)

        svc_result = await session.execute(
            select(ServiceSettings).where(ServiceSettings.id == 1)
        )
        svc = svc_result.scalar_one_or_none()
        if svc:
            emergency_stop = svc.emergency_stop

    except Exception:
        pass

    return HealthResponse(
        status="healthy" if db_status == "ok" else "degraded",
        version=_VERSION,
        database=db_status,
        worker_running=_WORKER_RUNNING,
        emergency_stop=emergency_stop,
        daily_videos_today=daily_videos,
        estimated_daily_spend_usd=daily_spend,
    )
