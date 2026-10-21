"""
Admin Jobs API
==============
View and manage video jobs. All endpoints require the admin API key.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.database import get_async_session
from app.models import VideoJob, PublishedVideo, VideoAsset, JobStatus
from app.schemas import VideoJobDetail, VideoJobRead, VideoAssetRead, PublishedVideoRead

router = APIRouter(prefix="/admin", tags=["Admin - Jobs"])


@router.get("/jobs", response_model=list[VideoJobRead])
async def list_jobs(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    """List video jobs with optional status filter."""
    query = select(VideoJob).order_by(desc(VideoJob.created_at)).limit(limit)
    if status:
        try:
            status_enum = JobStatus(status)
            query = query.where(VideoJob.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/jobs/{job_id}", response_model=VideoJobDetail)
async def get_job(
    job_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    result = await session.execute(select(VideoJob).where(VideoJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    """Retry a failed job."""
    result = await session.execute(select(VideoJob).where(VideoJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=400, detail=f"Job is {job.status.value}, not failed"
        )
    job.status = JobStatus.PENDING
    job.retry_count = 0
    job.next_retry_at = None
    job.failure_category = None
    job.error_details = None
    await session.commit()
    return {"message": f"Job {job_id} queued for retry"}


@router.get("/jobs/{job_id}/assets", response_model=list[VideoAssetRead])
async def get_job_assets(
    job_id: int,
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    result = await session.execute(
        select(VideoAsset).where(VideoAsset.job_id == job_id)
    )
    return result.scalars().all()


@router.get("/published", response_model=list[PublishedVideoRead])
async def list_published(
    limit: int = Query(default=20, le=100),
    session: AsyncSession = Depends(get_async_session),
    _: None = Depends(require_admin),
):
    result = await session.execute(
        select(PublishedVideo)
        .order_by(desc(PublishedVideo.created_at))
        .limit(limit)
    )
    return result.scalars().all()
