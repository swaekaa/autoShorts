"""
Autonomous Worker
=================
Persistent worker loop that:
1. Checks service state (emergency stop, enabled flag)
2. Checks budget and daily limits
3. Finds the next eligible job or creates one
4. Runs the pipeline
5. Sleeps or schedules the next run

Designed to run continuously in the cloud without human intervention.
A failed job does NOT stop the worker.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone
from typing import Any

from app.budget_manager import BudgetManager
from app.database import get_session
from app.gemini.client import GeminiClient
from app.logging_config import get_logger
from app.models import JobStatus, ServiceSettings, VideoJob
from app.pipeline import VideoPipeline
from app.quota_manager import QuotaManager, QuotaState, ServiceProvider
from app.services.job_service import JobService
from app.topic_manager import TopicManager
from app.video.asset_storage import AssetStorage

logger = get_logger(__name__)

_shutdown_requested = False


def _handle_signal(signum, frame):
    global _shutdown_requested
    logger.info("Shutdown signal received – finishing current job then stopping")
    _shutdown_requested = True


class Worker:
    def __init__(self, settings: Any):
        self._settings = settings
        self._gemini_client = GeminiClient(
            api_key=settings.gemini_api_key,
            text_model=settings.gemini_text_model,
            video_model=settings.gemini_video_model,
        )
        self._storage = AssetStorage(settings)
        self._active_jobs: int = 0

    async def run(self) -> None:
        """Main worker loop. Runs until shutdown signal or emergency stop."""
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        logger.info("Worker started")

        # Startup validation
        await self._startup_checks()

        while not _shutdown_requested:
            try:
                await self._tick()
            except Exception as exc:
                logger.exception(
                    "Unexpected worker tick error",
                    extra={"error": str(exc)[:500]},
                )

            poll_interval = self._settings.worker_poll_interval_seconds
            logger.debug(
                "Worker sleeping",
                extra={"seconds": poll_interval},
            )
            await asyncio.sleep(poll_interval)

        logger.info("Worker shutdown complete")

    async def _startup_checks(self) -> None:
        """Run startup checks and recovery."""
        async with await get_session() as session:
            # Seed topics if DB is empty
            topic_mgr = TopicManager(session)
            await topic_mgr.seed_topics()

            # Recover in-progress jobs (mark as pending for retry)
            job_svc = JobService(session)
            stuck_jobs = await job_svc.get_in_progress_jobs()
            for job in stuck_jobs:
                logger.warning(
                    "Recovering stuck job",
                    extra={"job_id": job.id, "stage": job.stage.value},
                )
                job.status = JobStatus.PENDING  # Will resume from last stage
            await session.commit()

            logger.info(
                "Startup checks complete",
                extra={"recovered_jobs": len(stuck_jobs)},
            )

    async def _tick(self) -> None:
        """One iteration of the worker loop."""
        async with await get_session() as session:
            # Check emergency stop
            from sqlalchemy import select
            settings_result = await session.execute(
                select(ServiceSettings).where(ServiceSettings.id == 1)
            )
            svc_settings = settings_result.scalar_one_or_none()
            if svc_settings and svc_settings.emergency_stop:
                logger.warning("Emergency stop active – skipping tick")
                return

            # Also check env-level emergency stop
            if self._settings.emergency_stop:
                logger.warning("Emergency stop (env) active – skipping tick")
                return

            # Check if service is enabled
            if svc_settings and not svc_settings.enabled:
                logger.debug("Service disabled – skipping tick")
                return

            # Check budget limits
            budget = BudgetManager(session, self._settings)
            can_gen, reason = await budget.can_generate()
            if not can_gen:
                logger.info("Budget limit reached", extra={"reason": reason})
                return

            # Check if we're at max concurrent jobs
            job_svc = JobService(session)
            queued_count = await job_svc.get_queued_count()
            if self._active_jobs >= self._settings.max_concurrent_generation_jobs:
                logger.debug(
                    "At max concurrent jobs",
                    extra={"active": self._active_jobs, "limit": self._settings.max_concurrent_generation_jobs},
                )
                return

            # Check video generation quota
            quota_mgr = QuotaManager(session, self._settings)
            video_state = await quota_mgr.get_state(ServiceProvider.GEMINI_VIDEO)
            if video_state not in (QuotaState.READY, QuotaState.GENERATING):
                remaining = await quota_mgr.get_cooldown_remaining(ServiceProvider.GEMINI_VIDEO)
                logger.info(
                    "Video quota unavailable",
                    extra={
                        "state": video_state.value,
                        "cooldown_remaining_seconds": remaining,
                    },
                )
                return

            # Check queue limit – don't fill queue during video outage
            if queued_count >= self._settings.max_queued_jobs:
                logger.debug(
                    "Queue at capacity",
                    extra={"queued": queued_count, "limit": self._settings.max_queued_jobs},
                )
                return

            # Get or create a job
            pending_jobs = await job_svc.get_pending_jobs(limit=1)
            if not pending_jobs:
                # Create a new job from an unused topic
                job = await self._create_new_job(session, job_svc)
                if job is None:
                    return
            else:
                job = pending_jobs[0]

            await session.commit()

        # Run the pipeline (outside the session context to avoid long transactions)
        await self._run_pipeline(job.id)

    async def _create_new_job(self, session, job_svc: JobService) -> VideoJob | None:
        """Select an unused topic and create a new job."""
        topic_mgr = TopicManager(session)
        unused = await topic_mgr.get_unused_topics(limit=10)

        if not unused:
            # Generate new topics via Gemini
            existing = await topic_mgr.get_all_topic_texts()
            from app.gemini.script_generator import ScriptGenerator
            script_gen = ScriptGenerator(self._gemini_client)
            new_suggestions = await script_gen.generate_additional_topics(existing, count=5)

            if new_suggestions:
                from app.models import TopicCategory
                for sugg in new_suggestions:
                    try:
                        cat_str = sugg.get("category", "mythology")
                        try:
                            cat = TopicCategory(cat_str)
                        except ValueError:
                            cat = TopicCategory.MYTHOLOGY
                        await topic_mgr.get_or_create_topic(
                            topic_text=sugg["text"],
                            category=cat,
                        )
                    except Exception as exc:
                        logger.warning("Failed to create topic", extra={"error": str(exc)})
                await session.commit()
                unused = await topic_mgr.get_unused_topics(limit=1)

        if not unused:
            logger.info("No unused topics available")
            return None

        topic = unused[0]
        job = await job_svc.create_job(topic)
        await session.flush()
        return job

    async def _run_pipeline(self, job_id: int) -> None:
        """Run the full pipeline for a job in its own session."""
        self._active_jobs += 1
        try:
            async with await get_session() as session:
                quota_mgr = QuotaManager(session, self._settings)
                storage = AssetStorage(self._settings)
                pipeline = VideoPipeline(
                    session=session,
                    settings=self._settings,
                    gemini_client=self._gemini_client,
                    quota_manager=quota_mgr,
                    storage=storage,
                )
                success = await pipeline.run_job(job_id)
                if success:
                    logger.info("Pipeline completed", extra={"job_id": job_id})
                else:
                    logger.warning("Pipeline did not complete", extra={"job_id": job_id})
        except Exception as exc:
            logger.exception(
                "Pipeline crash",
                extra={"job_id": job_id, "error": str(exc)[:500]},
            )
        finally:
            self._active_jobs -= 1
