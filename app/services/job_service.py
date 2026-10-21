"""
Job Service
===========
Database operations for video jobs: create, update, query.
Prevents duplicate jobs and enforces state machine transitions.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_config import get_logger
from app.models import (
    AssetType,
    FailureCategory,
    JobStage,
    JobStatus,
    PublicationStatus,
    PublishedVideo,
    Topic,
    VideoAsset,
    VideoJob,
)

logger = get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobService:
    def __init__(self, session: AsyncSession):
        self._db = session

    async def create_job(self, topic: Topic) -> VideoJob:
        """Create a new video job for a topic. Prevents duplicates via DB constraint."""
        # Check for existing active job for this topic
        result = await self._db.execute(
            select(VideoJob).where(
                and_(
                    VideoJob.topic_id == topic.id,
                    VideoJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            logger.warning(
                "Active job already exists for topic",
                extra={"topic_id": topic.id, "job_id": existing.id},
            )
            return existing

        job = VideoJob(
            topic_id=topic.id,
            stage=JobStage.TOPIC_SELECTED,
            status=JobStatus.PENDING,
        )
        self._db.add(job)
        await self._db.flush()
        logger.info(
            "Job created",
            extra={"job_id": job.id, "topic_id": topic.id},
        )
        return job

    async def update_job(
        self,
        job: VideoJob,
        stage: JobStage | None = None,
        status: JobStatus | None = None,
        script_data: dict | None = None,
        operation_id: str | None = None,
        failure_category: FailureCategory | None = None,
        error_details: str | None = None,
        estimated_cost_usd: float | None = None,
    ) -> VideoJob:
        """Update job state. All changes are applied atomically."""
        if stage is not None:
            job.stage = stage
        if status is not None:
            job.status = status
            if status == JobStatus.RUNNING and job.started_at is None:
                job.started_at = utcnow()
            if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.ABANDONED):
                job.completed_at = utcnow()
        if script_data is not None:
            job.script_data = script_data
        if operation_id is not None:
            job.generation_operation_id = operation_id
        if failure_category is not None:
            job.failure_category = failure_category
        if error_details is not None:
            job.error_details = error_details
        if estimated_cost_usd is not None:
            job.estimated_cost_usd = (job.estimated_cost_usd or 0.0) + estimated_cost_usd
        job.updated_at = utcnow()
        await self._db.flush()
        return job

    async def increment_retry(
        self, job: VideoJob, max_retries: int, next_retry_delay_seconds: int = 60
    ) -> bool:
        """
        Increment retry count. Returns True if still within limit, False if exhausted.
        """
        job.retry_count += 1
        job.next_retry_at = utcnow() + timedelta(seconds=next_retry_delay_seconds)
        job.updated_at = utcnow()
        await self._db.flush()

        if job.retry_count > max_retries:
            await self.update_job(job, status=JobStatus.FAILED)
            logger.error(
                "Job abandoned after max retries",
                extra={"job_id": job.id, "retry_count": job.retry_count},
            )
            return False
        return True

    async def add_asset(
        self,
        job: VideoJob,
        asset_type: AssetType,
        storage_key: str,
        mime_type: str,
        duration_seconds: float | None = None,
        width: int | None = None,
        height: int | None = None,
        file_size_bytes: int | None = None,
        checksum: str | None = None,
        validation_details: dict | None = None,
    ) -> VideoAsset:
        """Record a generated asset in the database."""
        asset = VideoAsset(
            job_id=job.id,
            asset_type=asset_type,
            storage_key=storage_key,
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            width=width,
            height=height,
            file_size_bytes=file_size_bytes,
            checksum=checksum,
            validation_status="valid" if validation_details and validation_details.get("passed") else "pending",
            validation_details=validation_details,
        )
        self._db.add(asset)
        await self._db.flush()
        return asset

    async def get_pending_jobs(self, limit: int = 5) -> list[VideoJob]:
        """Get jobs eligible for processing (pending or resumable)."""
        now = utcnow()
        result = await self._db.execute(
            select(VideoJob)
            .where(
                and_(
                    VideoJob.status.in_([JobStatus.PENDING, JobStatus.PAUSED]),
                    (VideoJob.next_retry_at.is_(None)) | (VideoJob.next_retry_at <= now),
                )
            )
            .order_by(VideoJob.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_in_progress_jobs(self) -> list[VideoJob]:
        """Get jobs currently marked as RUNNING (survived a crash if any)."""
        result = await self._db.execute(
            select(VideoJob).where(VideoJob.status == JobStatus.RUNNING)
        )
        return list(result.scalars().all())

    async def get_queued_count(self) -> int:
        """Count jobs in pending/running state."""
        result = await self._db.execute(
            select(func.count(VideoJob.id)).where(
                VideoJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED])
            )
        )
        return int(result.scalar_one() or 0)

    async def create_upload_intent(self, job: VideoJob, title: str, description: str) -> PublishedVideo:
        """
        Create a PublishedVideo record BEFORE initiating the upload.
        The upload_intent_token acts as an idempotency key.
        """
        # Check if intent already exists
        result = await self._db.execute(
            select(PublishedVideo).where(PublishedVideo.job_id == job.id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        intent_token = secrets.token_hex(32)
        published = PublishedVideo(
            job_id=job.id,
            title=title,
            description=description,
            publication_status=PublicationStatus.PENDING,
            upload_intent_token=intent_token,
            upload_started_at=utcnow(),
        )
        self._db.add(published)
        await self._db.flush()
        logger.info(
            "Upload intent created",
            extra={"job_id": job.id, "intent_token": intent_token[:8] + "..."},
        )
        return published

    async def complete_upload(
        self,
        published: PublishedVideo,
        youtube_video_id: str,
        video_url: str,
        privacy_status: str,
    ) -> PublishedVideo:
        """Update PublishedVideo after successful upload."""
        published.youtube_video_id = youtube_video_id
        published.video_url = video_url
        published.publication_status = PublicationStatus(privacy_status)
        published.upload_completed_at = utcnow()
        published.last_verified_at = utcnow()
        await self._db.flush()
        return published

    async def count_completed_today(self) -> int:
        """Count videos completed today (UTC)."""
        today_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = await self._db.execute(
            select(func.count(VideoJob.id)).where(
                and_(
                    VideoJob.status == JobStatus.COMPLETED,
                    VideoJob.completed_at >= today_start,
                )
            )
        )
        return int(result.scalar_one() or 0)
