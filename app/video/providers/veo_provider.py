"""
Google Veo Video Provider
=========================
Generates real, dynamic video footage for each scene using Google's Veo video model.
- Strictly sends scene-level action and camera descriptions (NOT entire storyboards).
- Polls asynchronous video operations.
- Downloads authentic MP4 video footage.
- Conforms and stitches independent scene clips into the full 10-second video.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, List, Optional

from google.genai import types as genai_types

from app.gemini.client import GeminiClient
from app.logging_config import get_logger
from app.schemas import SceneDescription
from app.video.providers.base import (
    BaseVideoProvider,
    ProviderCapabilities,
    ProviderCapabilityError,
)
from app.video.providers.motion_engine import MotionEngine

logger = get_logger(__name__)


class VeoVideoProvider(BaseVideoProvider):
    """
    True Text-to-Video generation using Google Veo.
    """

    def __init__(
        self,
        gemini_client: GeminiClient,
        settings: Any,
        storage_dir: Path,
    ):
        self._client = gemini_client
        self._settings = settings
        self._storage_dir = Path(storage_dir).resolve()
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        self._model = getattr(settings, "gemini_video_model", "veo-2.0-generate-001")
        self._engine = MotionEngine(
            width=settings.video_width,
            height=settings.video_height,
            fps=settings.video_fps,
        )

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name="google_veo",
            supports_text_to_video=True,
            supports_image_to_video=True,
            supports_text_to_image=False,
            supports_configurable_duration=False,  # Veo generates fixed length (5-8s)
            supports_vertical_aspect_ratio=True,
            supports_async_polling=True,
            supports_downloadable_video=True,
            target_resolution="1080x1920",
            target_fps=30,
        )

    async def validate_readiness(self) -> tuple[bool, str]:
        """Verify API key has permissions to query Veo."""
        if not hasattr(self._client, "_client"):
            return False, "Google GenAI SDK client is not initialized"
        try:
            # Check models list
            models = await asyncio.to_thread(lambda: list(self._client._client.models.list()))
            names = [getattr(m, "name", "") for m in models]
            matching = [n for n in names if "veo" in n.lower()]
            if not matching:
                return False, f"Account does not have access to Veo models (found: {len(models)} text/vision models)"
            return True, f"Veo models available: {', '.join(matching[:3])}"
        except Exception as exc:
            return False, f"Veo capability validation error: {exc}"

    def _build_scene_video_prompt(self, scene: SceneDescription) -> str:
        """
        Creates an actionable, cinematic visual motion prompt for a single scene.
        Excludes any titles, hashtags, contact sheets, or storyboard metadata.
        """
        visual = (scene.visual_description_english or scene.visual_description_hindi or "").strip()
        motion = (scene.motion_prompt or scene.camera_motion or "dynamic camera movement").strip()

        prompt = (
            f"Cinematic vertical video shot, 9:16 aspect ratio. {visual}. "
            f"Motion: {motion}. "
            f"Epic divine lighting, volumetric golden rays, realistic physical movement and particles. "
            f"Photorealistic 8k octane render. "
            f"Strict negative instructions: No text, no titles, no captions, no typography, "
            f"no storyboard panels, no contact sheet, no collage, no watermarks, no split screen."
        )
        return prompt[:480]

    async def generate_shot(
        self,
        scene: SceneDescription,
        output_path: Path,
        job_id: int,
    ) -> Path:
        """
        Generate a single video clip for a scene using Veo.
        """
        prompt = self._build_scene_video_prompt(scene)
        logger.info(
            "Submitting Veo scene video generation",
            extra={
                "job_id": job_id,
                "scene": scene.scene_number,
                "model": self._model,
                "duration": scene.duration_seconds,
            },
        )

        genai_client = self._client._client
        config = genai_types.GenerateVideosConfig(
            aspect_ratio="9:16",
            resolution="720p",
        )

        try:
            def _submit():
                return genai_client.models.generate_videos(
                    model=self._model,
                    prompt=prompt,
                    config=config,
                )

            operation = await asyncio.to_thread(_submit)
            op_name = getattr(operation, "name", str(id(operation)))
            logger.info("Veo operation submitted", extra={"op_name": op_name})

            # Poll operation until done
            completed_op = await self._poll_operation(operation, timeout_seconds=300)

            # Extract generated video
            videos = getattr(completed_op.response, "generated_videos", [])
            if not videos:
                raise ProviderCapabilityError("Veo completed operation returned no generated video")

            video_obj = videos[0]
            raw_clip = self._storage_dir / f"job_{job_id}_veo_raw_scene_{scene.scene_number}.mp4"

            def _download():
                genai_client.files.download(file=video_obj.video)
                video_obj.video.save(str(raw_clip.resolve()))

            await asyncio.to_thread(_download)

            # Conform clip to target duration and 1080x1920 30fps
            return self._conform_clip(raw_clip, output_path, scene.duration_seconds)

        except Exception as exc:
            logger.error("Veo scene generation failed", extra={"error": str(exc)}, exc_info=True)
            raise ProviderCapabilityError(f"Veo video generation failed for scene {scene.scene_number}: {exc}") from exc

    async def _poll_operation(self, operation: Any, timeout_seconds: int = 300) -> Any:
        start_time = time.monotonic()
        genai_client = self._client._client
        current_op = operation

        while True:
            if getattr(current_op, "done", False):
                return current_op

            if time.monotonic() - start_time > timeout_seconds:
                raise TimeoutError(f"Veo video generation timed out after {timeout_seconds}s")

            await asyncio.sleep(10)
            current_op = await asyncio.to_thread(lambda: genai_client.operations.get(current_op))

    def _conform_clip(self, input_path: Path, output_path: Path, target_duration: float) -> Path:
        """Trim/scale/pad clip to exact target duration and 1080x1920 30fps."""
        import subprocess
        from app.media.ffmpeg_utils import get_ffmpeg_path

        ffmpeg_bin = get_ffmpeg_path()
        filter_str = (
            f"scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps=30,trim=duration={target_duration:.3f},setpts=PTS-STARTPTS"
        )
        cmd = [
            ffmpeg_bin, "-y",
            "-i", str(input_path.resolve()),
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-t", f"{target_duration:.3f}",
            str(output_path.resolve()),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        if res.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"Clip conformance failed: {res.stderr[-300:]}")
        return output_path

    async def generate_video(
        self,
        scenes: List[SceneDescription],
        output_path: Path,
        job_id: int,
    ) -> Path:
        """Generate all scene clips and concatenate them into the 10-second video."""
        clip_paths: List[Path] = []
        for idx, scene in enumerate(scenes):
            shot_clip = self._storage_dir / f"job_{job_id}_scene_{idx}_final.mp4"
            rendered_clip = await self.generate_shot(scene, shot_clip, job_id)
            clip_paths.append(rendered_clip)

        return self._engine.concatenate_shot_clips(
            clip_paths=clip_paths,
            output_video_path=output_path,
            target_duration=float(self._settings.video_duration_seconds),
        )
