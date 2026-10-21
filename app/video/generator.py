"""
Video Generator
===============
Supports two visual engines:
1. 'free_motion' (DEFAULT, 100% Free Tier):
   Generates vertical 9:16 devotional imagery (via free Pollinations.ai or procedural
   sacred color gradients) with smooth Ken Burns pan-and-zoom motion rendered via FFmpeg.
   Zero API keys, zero cost, instant availability.

2. 'veo' (Optional Google Veo):
   Submits to Google's Veo video generation model via the google-genai SDK.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from app.gemini.client import GeminiClient
from app.logging_config import get_logger
from app.media.ffmpeg_utils import get_ffmpeg_path
from app.quota_manager import (
    QuotaEventType,
    QuotaManager,
    ServiceProvider,
    classify_api_error,
)
from app.schemas import GeneratedScript

logger = get_logger(__name__)


class VideoGenerationError(Exception):
    """Raised when video generation fails unrecoverably."""


class VideoGenerator:
    def __init__(
        self,
        client: GeminiClient,
        quota_manager: QuotaManager,
        settings: Any,
        storage_dir: str = "./storage/generated",
    ):
        self._client = client
        self._quota = quota_manager
        self._settings = settings
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)

    def _build_video_prompt(self, script: GeneratedScript) -> str:
        """
        Build an English visual prompt from scene descriptions.
        """
        scene_descriptions = []
        for scene in script.scenes:
            desc = scene.visual_description_english.strip()
            if desc:
                scene_descriptions.append(desc)

        combined = ". ".join(scene_descriptions)
        style_prefix = (
            "Cinematic vertical 9:16 sacred Hindu devotional art. "
            "Vibrant saffron, divine golden aura, detailed Indian spiritual iconography, "
            "sacred temple lighting, 8k resolution masterpiece. "
        )
        full_prompt = style_prefix + combined
        if len(full_prompt) > 400:
            full_prompt = full_prompt[:397] + "..."
        return full_prompt

    async def _generate_free_motion_video(self, script: GeneratedScript, job_id: int) -> Path:
        """
        100% Free Tier: Generates 10.0s 1080x1920 30fps vertical motion video
        using devotional imagery and FFmpeg Ken Burns pan/zoom.
        """
        raw_output = self._storage_dir / f"job_{job_id}_raw_video.mp4"
        image_path = self._storage_dir / f"job_{job_id}_art.jpg"

        prompt = self._build_video_prompt(script)
        logger.info("Generating free motion visuals", extra={"job_id": job_id, "prompt": prompt[:80]})

        # Step 1: Download devotional image from free Pollinations AI service
        downloaded = False
        try:
            encoded_prompt = urllib.parse.quote(prompt)
            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&model=flux&nologo=true&seed={job_id}"
            async with httpx.AsyncClient(timeout=35.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and len(resp.content) > 10000:
                    image_path.write_bytes(resp.content)
                    downloaded = True
                    logger.info("Free devotional art downloaded successfully", extra={"bytes": len(resp.content)})
        except Exception as exc:
            logger.warning("Free art download skipped or timed out; generating procedural backdrop", extra={"error": str(exc)})

        # Step 2: Render 10.0s 1080x1920 30fps video using FFmpeg
        if downloaded and image_path.exists():
            # Ken Burns slow zoom-in on the sacred art
            filter_graph = (
                "scale=1080:1920:force_original_aspect_ratio=increase,"
                "crop=1080:1920,"
                "zoompan=z='min(zoom+0.0010,1.18)':d=300:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
                "format=yuv420p"
            )
            ffmpeg_bin = get_ffmpeg_path()
            cmd = [
                ffmpeg_bin, "-y",
                "-loop", "1",
                "-i", str(image_path),
                "-vf", filter_graph,
                "-t", "10.0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                str(raw_output),
            ]
        else:
            # Fallback procedural radiant backdrop with sacred gold & saffron glow
            filter_graph = (
                "color=c=#1A0B2E:s=1080x1920:d=10,"
                "drawbox=x=80:y=160:w=920:h=1600:color=#FF6F00@0.15:t=fill,"
                "drawbox=x=180:y=360:w=720:h=1200:color=#FFD700@0.2:t=fill,"
                "format=yuv420p"
            )
            ffmpeg_bin = get_ffmpeg_path()
            cmd = [
                ffmpeg_bin, "-y",
                "-f", "lavfi",
                "-i", filter_graph,
                "-t", "10.0",
                "-c:v", "libx264",
                "-preset", "fast",
                "-pix_fmt", "yuv420p",
                str(raw_output),
            ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not raw_output.exists():
            logger.error("FFmpeg visual motion rendering failed", extra={"stderr": proc.stderr[:300]})
            raise VideoGenerationError(f"FFmpeg motion rendering failed: {proc.stderr[:200]}")

        logger.info("Free motion video generated successfully", extra={"path": str(raw_output)})
        return raw_output

    async def submit_generation(
        self, script: GeneratedScript, job_id: int
    ) -> str:
        """
        Submit or create video generation.
        In 'free_motion' mode, renders the 10s motion clip immediately.
        In 'veo' mode, submits to the Veo API.
        """
        mode = getattr(self._settings, "visual_generator", "free_motion")

        if mode == "free_motion":
            video_path = await self._generate_free_motion_video(script, job_id)
            return f"free_motion:{video_path.name}"

        # Veo mode
        if not await self._quota.can_generate(ServiceProvider.GEMINI_VIDEO):
            remaining = await self._quota.get_cooldown_remaining(ServiceProvider.GEMINI_VIDEO)
            raise VideoGenerationError(
                f"Video generation quota unavailable. Cooldown: {remaining}s"
            )

        prompt = self._build_video_prompt(script)
        logger.info(
            "Submitting Veo video generation",
            extra={"job_id": job_id, "model": self._settings.gemini_video_model},
        )

        try:
            operation = self._client.submit_video_generation(
                prompt=prompt,
                aspect_ratio="9:16",
                duration_seconds=8,
                resolution="1080p",
            )
            operation_name = getattr(operation, "name", str(id(operation)))
            await self._quota.record_event(
                provider=ServiceProvider.GEMINI_VIDEO,
                event_type=QuotaEventType.REQUEST,
                model_id=self._settings.gemini_video_model,
            )
            return operation_name

        except Exception as exc:
            event_type, error_code, retry_after = classify_api_error(exc)
            await self._quota.record_event(
                provider=ServiceProvider.GEMINI_VIDEO,
                event_type=event_type,
                error_code=error_code,
                retry_after_seconds=retry_after,
            )
            if event_type == QuotaEventType.QUOTA_EXCEEDED:
                raise VideoGenerationError(f"Video quota exhausted: {exc}") from exc
            raise

    async def poll_until_complete(
        self,
        operation_name: str,
        timeout_seconds: int = 600,
    ) -> Any:
        """
        Poll the operation until done. For free_motion, resolves immediately.
        """
        if str(operation_name).startswith("free_motion"):
            if ":" in operation_name:
                filename = operation_name.split(":", 1)[1]
            else:
                filename = operation_name.replace("free_motion_", "")
                if not (self._storage_dir / filename).exists():
                    # Handle possible job_id prefix e.g. 4_job_4_raw_video.mp4
                    parts = filename.split("_", 1)
                    if len(parts) > 1 and (self._storage_dir / parts[1]).exists():
                        filename = parts[1]

            path = self._storage_dir / filename
            return {"type": "free_motion", "path": str(path)}

        poll_interval = self._settings.video_gen_poll_interval_seconds
        start_time = time.monotonic()
        operation = None

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed > timeout_seconds:
                raise VideoGenerationError(f"Video generation timed out after {timeout_seconds}s")

            try:
                if operation is None:
                    operation = self._client.raw_client.operations.get(name=operation_name)
                else:
                    operation = self._client.poll_video_operation(operation)

                if operation.done:
                    await self._quota.record_event(
                        provider=ServiceProvider.GEMINI_VIDEO,
                        event_type=QuotaEventType.SUCCESS,
                        model_id=self._settings.gemini_video_model,
                    )
                    return operation

            except Exception as exc:
                event_type, error_code, retry_after = classify_api_error(exc)
                if event_type == QuotaEventType.QUOTA_EXCEEDED:
                    await self._quota.record_event(
                        provider=ServiceProvider.GEMINI_VIDEO,
                        event_type=event_type,
                        error_code=error_code,
                        retry_after_seconds=retry_after,
                    )
                    raise VideoGenerationError(f"Quota exceeded during polling: {exc}") from exc

            await asyncio.sleep(poll_interval)

    async def download_video(
        self, operation: Any, job_id: int, clip_index: int = 0
    ) -> Path:
        """
        Returns local file path of generated clip.
        """
        if isinstance(operation, dict) and operation.get("type") == "free_motion":
            path = Path(operation.get("path", ""))
            if path.exists():
                return path
            fallback = self._storage_dir / f"job_{job_id}_raw_video.mp4"
            if fallback.exists():
                return fallback
            raise VideoGenerationError(f"Free motion video file not found at {path}")

        videos = self._client.get_generated_video(operation)
        if not videos:
            raise VideoGenerationError("No videos in operation response")

        video_obj = videos[0]
        output_path = self._storage_dir / f"job_{job_id}_raw_clip_{clip_index}.mp4"
        self._client.download_video(video_obj, str(output_path))
        return output_path
