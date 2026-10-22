"""
Main Video Pipeline
===================
Orchestrates the full end-to-end flow for a single video job:

1. Generate Hindi script via Gemini
2. Synthesize narration via Google TTS
3. Submit video generation to Veo
4. Poll until complete and download
5. Generate background music
6. Generate subtitles
7. Render final 10-second Short via FFmpeg
8. Validate the output
9. Upload to YouTube (if enabled)

All stages are persisted to the database so a crash can resume
from the last completed stage without re-doing expensive operations.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.background_music import BackgroundMusicGenerator
from app.audio.narration import NarrationGenerator
from app.budget_manager import (
    BudgetManager,
    estimate_script_generation_cost,
    estimate_tts_cost,
    estimate_video_generation_cost,
)
from app.gemini.client import GeminiClient
from app.gemini.metadata_generator import MetadataGenerator
from app.gemini.script_generator import ScriptGenerator
from app.logging_config import get_logger
from app.media.renderer import VideoRenderer
from app.media.subtitles import generate_subtitles
from app.media.validator import MediaValidator
from app.models import AssetType, FailureCategory, JobStage, JobStatus, Topic
from app.quota_manager import (
    QuotaEventType,
    QuotaManager,
    ServiceProvider,
    classify_api_error,
)
from app.schemas import GeneratedScript
from app.services.job_service import JobService
from app.topic_manager import TopicManager
from app.video.asset_storage import AssetStorage
from app.video.generator import VideoGenerationError, VideoGenerator

logger = get_logger(__name__)

WORK_DIR = Path("./storage/working")


class PipelineError(Exception):
    """Non-retryable pipeline failure."""


class PipelineQuotaError(Exception):
    """Quota-related pipeline failure – should pause and retry later."""


class VideoPipeline:
    def __init__(
        self,
        session: AsyncSession,
        settings: Any,
        gemini_client: GeminiClient,
        quota_manager: QuotaManager,
        storage: AssetStorage,
    ):
        self._db = session
        self._settings = settings
        self._client = gemini_client
        self._quota = quota_manager
        self._storage = storage

        self._script_gen = ScriptGenerator(gemini_client)
        self._meta_gen = MetadataGenerator(gemini_client)
        self._narration_gen = NarrationGenerator(settings, quota_manager)
        self._music_gen = BackgroundMusicGenerator(settings)
        self._video_gen = VideoGenerator(gemini_client, quota_manager, settings)
        self._renderer = VideoRenderer(settings)
        self._validator = MediaValidator(settings)
        self._job_svc = JobService(session)
        self._budget = BudgetManager(session, settings)

        WORK_DIR.mkdir(parents=True, exist_ok=True)

    async def run_job(self, job_id: int) -> bool:
        """
        Run or resume a video job by ID.
        Returns True on success, False on failure.
        Persists progress at each stage.
        """
        from sqlalchemy import select
        from app.models import VideoJob

        result = await self._db.execute(
            select(VideoJob).where(VideoJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("Job not found", extra={"job_id": job_id})
            return False

        # Get the topic
        from app.models import Topic as TopicModel
        topic_result = await self._db.execute(
            select(TopicModel).where(TopicModel.id == job.topic_id)
        )
        topic = topic_result.scalar_one_or_none()
        if topic is None:
            logger.error("Topic not found for job", extra={"job_id": job_id})
            return False

        await self._job_svc.update_job(job, status=JobStatus.RUNNING)
        await self._db.commit()

        work_dir = WORK_DIR / f"job_{job_id}"
        work_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ── Stage 1: Script Generation ────────────────────────
            script: GeneratedScript | None = None
            if job.stage == JobStage.TOPIC_SELECTED:
                script = await self._generate_script(job, topic, work_dir)
                if not script:
                    return False
            else:
                # Restore script from DB
                if job.script_data:
                    script = GeneratedScript.model_validate(job.script_data)

            if script is None:
                logger.error("No script available", extra={"job_id": job_id})
                await self._job_svc.update_job(
                    job,
                    status=JobStatus.FAILED,
                    failure_category=FailureCategory.GENERATION_ERROR,
                    error_details="Script data missing",
                )
                return False

            # ── Stage 2: TTS Narration ────────────────────────────
            narration_path: Path | None = None
            narration_duration: float = 10.0
            if job.stage in (JobStage.TOPIC_SELECTED, JobStage.SCRIPT_GENERATED):
                narration_path, narration_duration = await self._generate_narration(
                    job, script, work_dir
                )
                if narration_path is None:
                    return False

            # ── Stage 3: Video Generation ─────────────────────────
            raw_video_path: Path | None = None
            if job.stage in (
                JobStage.TOPIC_SELECTED,
                JobStage.SCRIPT_GENERATED,
                JobStage.TTS_GENERATED,
            ):
                raw_video_path = await self._generate_video(job, script, work_dir)
                if raw_video_path is None:
                    # Job paused for quota – not a failure
                    await self._db.commit()
                    return False
            else:
                # Resume: re-download if we have an operation ID
                if job.generation_operation_id and job.stage == JobStage.VIDEO_POLLING:
                    raw_video_path = await self._resume_video_polling(job, work_dir)
                else:
                    # Already downloaded, look for the file
                    candidate = work_dir / "raw_video.mp4"
                    if candidate.exists():
                        raw_video_path = candidate

            if raw_video_path is None or not raw_video_path.exists():
                logger.error("Raw video not found", extra={"job_id": job_id})
                await self._job_svc.update_job(
                    job,
                    status=JobStatus.FAILED,
                    failure_category=FailureCategory.GENERATION_ERROR,
                    error_details="Raw video file missing",
                )
                return False

            # Recover narration path if resuming
            if narration_path is None:
                narration_path = work_dir / "narration.aac"
                if not narration_path.exists():
                    narration_path, narration_duration = await self._generate_narration(
                        job, script, work_dir
                    )

            # ── Stage 4: Background Music ─────────────────────────
            music_path = work_dir / "background_music.aac"
            if not music_path.exists():
                self._music_gen.get_or_generate(
                    output_path=music_path,
                    duration_seconds=float(self._settings.video_duration_seconds),
                    mood="devotional",
                )

            # ── Stage 5: Subtitles ────────────────────────────────
            subtitle_path = work_dir / "subtitles.ass"
            if not subtitle_path.exists():
                generate_subtitles(
                    script=script,
                    output_path=subtitle_path,
                    total_duration=float(self._settings.video_duration_seconds),
                )

            # ── Stage 6: Render ───────────────────────────────────
            final_path: Path | None = None
            if job.stage not in (JobStage.RENDERED, JobStage.VALIDATED, JobStage.UPLOAD_PENDING, JobStage.UPLOADED):
                final_path = await self._render_video(
                    job, raw_video_path, narration_path, music_path, subtitle_path,
                    narration_duration, work_dir
                )
                if final_path is None:
                    return False
            else:
                final_path = work_dir / "final_video.mp4"

            # ── Stage 7: Validate ─────────────────────────────────
            if job.stage not in (JobStage.VALIDATED, JobStage.UPLOAD_PENDING, JobStage.UPLOADED):
                valid = await self._validate_video(job, final_path)
                if not valid:
                    return False

            # ── Stage 8: Upload ───────────────────────────────────
            if (
                self._settings.auto_publish
                and self._settings.youtube_upload_enabled
                and job.stage != JobStage.UPLOADED
            ):
                await self._upload_to_youtube(job, script, final_path)

            # Mark complete
            await self._job_svc.update_job(job, status=JobStatus.COMPLETED)
            await self._db.commit()
            logger.info("Job completed successfully", extra={"job_id": job_id})
            return True

        except PipelineQuotaError as exc:
            logger.warning(
                "Job paused due to quota",
                extra={"job_id": job_id, "reason": str(exc)},
            )
            await self._job_svc.update_job(
                job,
                status=JobStatus.PAUSED,
                failure_category=FailureCategory.QUOTA_EXHAUSTED,
                error_details=str(exc),
            )
            await self._db.commit()
            return False

        except Exception as exc:
            logger.exception(
                "Unexpected pipeline error",
                extra={"job_id": job_id, "error": str(exc)[:500]},
            )
            await self._job_svc.update_job(
                job,
                status=JobStatus.FAILED,
                failure_category=FailureCategory.UNKNOWN,
                error_details=str(exc)[:2000],
            )
            await self._db.commit()
            return False

    # ── Private stage methods ────────────────────────────────────

    async def _generate_script(self, job, topic, work_dir: Path) -> GeneratedScript | None:
        logger.info("Stage: script generation", extra={"job_id": job.id})
        topic_mgr = TopicManager(self._db)
        existing = await topic_mgr.get_all_topic_texts()

        try:
            script = await self._script_gen.generate_script(
                topic=topic.topic_text,
                category=topic.category,
                existing_topics=existing,
            )
            cost = estimate_script_generation_cost(None)
            await self._quota.record_event(
                provider=ServiceProvider.GEMINI_TEXT,
                event_type=QuotaEventType.SUCCESS,
                model_id=self._settings.gemini_text_model,
                estimated_cost_usd=cost,
            )
            await self._job_svc.update_job(
                job,
                stage=JobStage.SCRIPT_GENERATED,
                script_data=script.model_dump(),
                estimated_cost_usd=cost,
            )
            await self._db.commit()
            return script

        except Exception as exc:
            logger.error(
                "Script generation failed",
                extra={"job_id": job.id, "error": str(exc)[:500]},
                exc_info=True,
            )
            event_type, error_code, retry_after = classify_api_error(exc)
            await self._quota.record_event(
                provider=ServiceProvider.GEMINI_TEXT,
                event_type=event_type,
                error_code=error_code,
                retry_after_seconds=retry_after,
            )
            if event_type == QuotaEventType.QUOTA_EXCEEDED:
                raise PipelineQuotaError(f"Gemini text quota: {exc}") from exc
            await self._job_svc.update_job(
                job,
                status=JobStatus.FAILED,
                failure_category=FailureCategory.GENERATION_ERROR,
                error_details=str(exc)[:1000],
            )
            await self._db.commit()
            return None

    async def _generate_narration(self, job, script, work_dir: Path):
        logger.info("Stage: narration", extra={"job_id": job.id})
        narration_path = work_dir / "narration.aac"
        if narration_path.exists():
            return narration_path, self._narration_gen._get_audio_duration(str(narration_path))

        try:
            path, duration = await self._narration_gen.synthesize(
                text=script.hindi_narration,
                output_path=narration_path,
            )
            cost = 0.0 if getattr(self._settings, "tts_provider", "edge") == "edge" else estimate_tts_cost(len(script.hindi_narration))
            await self._quota.record_event(
                provider=ServiceProvider.GOOGLE_TTS,
                event_type=QuotaEventType.SUCCESS,
                estimated_cost_usd=cost,
            )
            await self._job_svc.update_job(
                job,
                stage=JobStage.TTS_GENERATED,
                estimated_cost_usd=cost,
            )
            await self._db.commit()

            if duration > self._settings.video_duration_seconds + 1.0:
                logger.warning(
                    "Narration exceeds 10s",
                    extra={"duration": duration, "job_id": job.id},
                )
            return path, duration

        except Exception as exc:
            logger.error(
                "TTS failed",
                extra={"job_id": job.id, "error": str(exc)[:500]},
            )
            await self._job_svc.update_job(
                job,
                status=JobStatus.FAILED,
                failure_category=FailureCategory.GENERATION_ERROR,
                error_details=f"TTS: {exc}",
            )
            return None, 0.0

    async def _generate_video(self, job, script, work_dir: Path) -> Path | None:
        logger.info("Stage: video generation submit", extra={"job_id": job.id})
        try:
            op_name = await self._video_gen.submit_generation(script, job.id)
            await self._job_svc.update_job(
                job,
                stage=JobStage.VIDEO_SUBMITTED,
                operation_id=op_name,
            )
            await self._db.commit()
        except VideoGenerationError as exc:
            if "quota" in str(exc).lower():
                raise PipelineQuotaError(str(exc)) from exc
            await self._job_svc.update_job(
                job,
                status=JobStatus.FAILED,
                failure_category=FailureCategory.GENERATION_ERROR,
                error_details=str(exc),
            )
            return None

        # Poll
        try:
            await self._job_svc.update_job(job, stage=JobStage.VIDEO_POLLING)
            await self._db.commit()
            operation = await self._video_gen.poll_until_complete(
                operation_name=job.generation_operation_id,
                timeout_seconds=self._settings.max_job_duration_minutes * 60,
            )
        except VideoGenerationError as exc:
            raise PipelineQuotaError(str(exc)) from exc

        # Download
        raw_path = await self._video_gen.download_video(operation, job.id)
        final_raw = work_dir / "raw_video.mp4"
        import shutil
        shutil.copy2(str(raw_path), str(final_raw))

        cost = 0.0 if getattr(self._settings, "visual_generator", "free_motion") == "free_motion" else estimate_video_generation_cost(self._settings.video_duration_seconds)
        storage_key = self._storage.make_storage_key(job.id, "raw_video", "mp4")
        self._storage.upload(final_raw, storage_key)

        await self._job_svc.add_asset(
            job,
            asset_type=AssetType.RAW_VIDEO,
            storage_key=storage_key,
            mime_type="video/mp4",
        )
        await self._job_svc.update_job(
            job,
            stage=JobStage.VIDEO_DOWNLOADED,
            estimated_cost_usd=cost,
        )
        await self._db.commit()
        return final_raw

    async def _resume_video_polling(self, job, work_dir: Path) -> Path | None:
        """Resume polling an existing operation ID after a crash."""
        logger.info("Resuming video polling", extra={"job_id": job.id, "op": job.generation_operation_id})
        try:
            operation = await self._video_gen.poll_until_complete(
                operation_name=job.generation_operation_id
            )
            raw_path = await self._video_gen.download_video(operation, job.id)
            final_raw = work_dir / "raw_video.mp4"
            import shutil
            shutil.copy2(str(raw_path), str(final_raw))
            await self._job_svc.update_job(job, stage=JobStage.VIDEO_DOWNLOADED)
            await self._db.commit()
            return final_raw
        except Exception as exc:
            logger.error("Resume polling failed", extra={"error": str(exc)})
            raise PipelineQuotaError(str(exc)) from exc

    async def _render_video(self, job, raw_video, narration, music, subtitles, narration_dur, work_dir):
        logger.info("Stage: render", extra={"job_id": job.id})
        output = work_dir / "final_video.mp4"
        try:
            self._renderer.render_final_video(
                raw_video_path=raw_video,
                narration_audio_path=narration,
                background_music_path=music,
                subtitle_path=subtitles,
                output_path=output,
                narration_duration=narration_dur,
            )
            storage_key = self._storage.make_storage_key(job.id, "final_video", "mp4")
            self._storage.upload(output, storage_key)
            checksum = AssetStorage.compute_checksum(output)
            await self._job_svc.add_asset(
                job,
                asset_type=AssetType.FINAL_VIDEO,
                storage_key=storage_key,
                mime_type="video/mp4",
                file_size_bytes=output.stat().st_size,
                checksum=checksum,
            )
            await self._job_svc.update_job(job, stage=JobStage.RENDERED)
            await self._db.commit()
            return output
        except Exception as exc:
            logger.error("Render failed", extra={"job_id": job.id, "error": str(exc)[:500]})
            await self._job_svc.update_job(
                job,
                status=JobStatus.FAILED,
                failure_category=FailureCategory.GENERATION_ERROR,
                error_details=f"Render: {exc}",
            )
            return None

    async def _validate_video(self, job, final_path: Path) -> bool:
        logger.info("Stage: validation & quality gate", extra={"job_id": job.id})
        from app.media.quality_gate import QualityGate

        subtitle_path = final_path.parent / "subtitles.ass"
        gate = QualityGate(self._settings)
        quality_result = gate.inspect_video(final_path, subtitle_path=subtitle_path if subtitle_path.exists() else None)

        if quality_result.passed:
            await self._job_svc.update_job(job, stage=JobStage.VALIDATED)
            await self._db.commit()
            return True
        else:
            error_msg = "; ".join(quality_result.errors)
            logger.error(
                "Quality gate validation failed",
                extra={"job_id": job.id, "errors": quality_result.errors, "warnings": quality_result.warnings},
            )
            await self._job_svc.update_job(
                job,
                status=JobStatus.FAILED,
                failure_category=FailureCategory.VALIDATION_ERROR,
                error_details=error_msg,
            )
            await self._db.commit()
            return False

    async def _upload_to_youtube(self, job, script: GeneratedScript, final_path: Path):
        from app.youtube.oauth import YouTubeOAuth
        from app.youtube.uploader import YouTubeUploader, UploadQuotaError, ChannelVerificationError

        logger.info("Stage: YouTube upload", extra={"job_id": job.id})
        try:
            oauth = YouTubeOAuth(self._settings)
            uploader = YouTubeUploader(oauth, self._quota, self._settings)
            await uploader.verify_channel_identity()

            metadata = await self._meta_gen.generate_youtube_metadata(script)
            published = await self._job_svc.create_upload_intent(
                job, metadata["title"], metadata.get("description", "")
            )

            await self._job_svc.update_job(job, stage=JobStage.UPLOAD_PENDING)
            await self._db.commit()

            result = await uploader.upload_video(
                video_path=final_path,
                title=metadata["title"],
                description=metadata.get("description", ""),
                tags=metadata.get("tags", []),
                category_id=metadata.get("category_id", 27),
                privacy_status=self._settings.video_privacy_status,
            )

            await self._job_svc.complete_upload(
                published,
                youtube_video_id=result["video_id"],
                video_url=result["url"],
                privacy_status=self._settings.video_privacy_status,
            )
            await self._job_svc.update_job(job, stage=JobStage.UPLOADED)
            await self._db.commit()
            logger.info(
                "Video uploaded",
                extra={"job_id": job.id, "url": result["url"]},
            )

        except (UploadQuotaError,) as exc:
            raise PipelineQuotaError(f"YouTube quota: {exc}") from exc
        except ChannelVerificationError as exc:
            raise PipelineError(f"Channel verification failed: {exc}") from exc
        except Exception as exc:
            logger.error("Upload failed", extra={"error": str(exc)[:500]})
            await self._job_svc.update_job(
                job,
                failure_category=FailureCategory.UPLOAD_ERROR,
                error_details=str(exc)[:1000],
            )
