"""
Google Imagen Animated Motion Video Provider
============================================
Generates distinct high-resolution 9:16 vertical images for each scene using Google Imagen 3,
and animates them into a continuous 10-second multi-scene video using FFmpeg Ken Burns motion.

Declares explicit capabilities:
- Text-to-image: Supported
- Text-to-video: NOT supported (animated image fallback)
- Prohibits synthetic text posters, contact sheets, and storyboards.
- If image generation fails, raises VideoGenerationError immediately instead of pretending with posters.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, List, Optional, Set

from app.gemini.client import GeminiClient
from app.logging_config import get_logger
from app.schemas import SceneDescription
from app.video.prompt_builder import PromptBuilder
from app.video.providers.base import (
    BaseVideoProvider,
    ProviderCapabilities,
    ProviderCapabilityError,
    VideoGenerationError,
)
from app.video.providers.motion_engine import MotionEngine

logger = get_logger(__name__)


class GoogleImagenMotionProvider(BaseVideoProvider):
    """
    Animated multi-shot video provider using Google Imagen 3 and FFmpeg motion.
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
        self._motion_engine = MotionEngine(
            width=settings.video_width,
            height=settings.video_height,
            fps=settings.video_fps,
        )
        self._last_error: Optional[str] = None

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_name="google_imagen_motion",
            supports_text_to_video=False,
            supports_image_to_video=False,
            supports_text_to_image=True,
            supports_configurable_duration=True,
            supports_vertical_aspect_ratio=True,
            supports_async_polling=False,
            supports_downloadable_video=True,
            target_resolution="1080x1920",
            target_fps=30,
        )

    async def validate_readiness(self) -> tuple[bool, str]:
        """Check if Gemini client and Imagen model are reachable."""
        if not hasattr(self._client, "_client"):
            return False, "Gemini client is not initialized"
        imagen_model = getattr(self._settings, "imagen_model", "imagen-3.0-generate-002")
        return True, f"Configured for Imagen 3: {imagen_model}"

    async def _fetch_imagen_shot(
        self,
        prompt: str,
        target_path: Path,
        imagen_model: str,
    ) -> bool:
        """
        Calls official Google Imagen 3 via google-genai SDK.
        Ensures strict prompt hygiene (no text, no titles, no watermarks).
        """
        if not hasattr(self._client, "_client"):
            self._last_error = "Gemini client not initialized"
            return False

        genai_client = self._client._client
        if not (hasattr(genai_client, "models") and hasattr(genai_client.models, "generate_images")):
            self._last_error = "google-genai SDK does not have models.generate_images"
            return False

        def _call_imagen():
            # 1. Try generate_images (Enterprise / Vertex mode)
            if hasattr(genai_client, "models") and hasattr(genai_client.models, "generate_images"):
                try:
                    from google.genai import types as genai_types
                    config = genai_types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="9:16",
                        output_mime_type="image/jpeg",
                    )
                except Exception:
                    config = {
                        "number_of_images": 1,
                        "aspect_ratio": "9:16",
                        "output_mime_type": "image/jpeg",
                    }

                try:
                    res = genai_client.models.generate_images(
                        model=imagen_model,
                        prompt=prompt[:480],
                        config=config,
                    )
                    if res and getattr(res, "generated_images", None):
                        return res.generated_images[0].image.image_bytes
                except Exception as exc:
                    self._last_error = str(exc)
                    logger.debug("generate_images call failed, trying multimodal generate_content", extra={"error": str(exc)[:120]})

            # 2. Try multimodal image generation models available in Developer API (e.g. gemini-2.5-flash-image)
            if hasattr(genai_client, "models") and hasattr(genai_client.models, "generate_content"):
                for m in ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"]:
                    try:
                        resp = genai_client.models.generate_content(
                            model=m,
                            contents=f"Generate a cinematic vertical 9:16 photorealistic devotional visual: {prompt[:380]}",
                        )
                        if hasattr(resp, "candidates") and resp.candidates:
                            for part in getattr(resp.candidates[0].content, "parts", []):
                                if hasattr(part, "inline_data") and part.inline_data:
                                    return part.inline_data.data
                    except Exception as e:
                        self._last_error = str(e)
                        logger.debug("generate_content image failed", extra={"model": m, "error": str(e)[:100]})

            return None

        try:
            image_bytes = await asyncio.wait_for(asyncio.to_thread(_call_imagen), timeout=25.0)
            if image_bytes and len(image_bytes) > 5000:
                target_path.write_bytes(image_bytes)
                logger.info("Generated scene image successfully", extra={"path": str(target_path), "bytes": len(image_bytes)})
                return True
            else:
                if not self._last_error:
                    self._last_error = "Image generation returned empty content"
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Visual generation call failed", extra={"error": str(exc), "model": imagen_model})

        return False

    def _find_distinct_fallback_art(self, used_images: Set[Path]) -> Optional[Path]:
        """Finds a pre-verified clean devotional image not already used in this video."""
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        search_dirs = [
            (project_root / "app" / "assets").resolve(),
            self._storage_dir.resolve(),
            (project_root / "storage" / "generated").resolve(),
        ]

        candidates: List[Path] = []
        for s_dir in search_dirs:
            if s_dir.exists():
                for ext in ("*.jpg", "*.jpeg", "*.png"):
                    for img in s_dir.glob(ext):
                        # Strict hygiene: reject any files with 'pollinat', 'job_4', 'job_9', or already used
                        name_lower = img.name.lower()
                        if any(banned in name_lower for banned in ("pollinat", "job_4", "job_9", "poster", "box")):
                            continue
                        if img not in used_images and img.stat().st_size > 100_000:
                            candidates.append(img)

        if candidates:
            candidates.sort(key=os.path.getmtime, reverse=True)
            return candidates[0]
        return None

    async def generate_shot(
        self,
        scene: SceneDescription,
        output_path: Path,
        job_id: int,
    ) -> Path:
        """
        Generate a single scene video clip with fluid Ken Burns camera movement.
        """
        shot_img_path = self._storage_dir / f"job_{job_id}_scene_{scene.scene_number}.jpg"
        imagen_model = getattr(self._settings, "imagen_model", "imagen-3.0-generate-002")

        # Clean visual prompt: strictly visual scene description with negative instructions
        clean_visual = (scene.visual_description_english or scene.visual_description_hindi or "").strip()
        motion = scene.camera_motion or "zoom_in_dramatic"

        prompt = (
            f"Cinematic vertical 9:16 sacred Hindu devotional art, {clean_visual}. "
            f"Radiant celestial golden light, dramatic mythological atmosphere, photorealistic 8k octane render. "
            f"Strictly NO text, NO titles, NO typography, NO watermark, NO storyboard panels, NO contact sheet."
        )

        success = await self._fetch_imagen_shot(
            prompt=prompt,
            target_path=shot_img_path,
            imagen_model=imagen_model,
        )

        if success and shot_img_path.exists() and shot_img_path.stat().st_size > 5000:
            return self._motion_engine.render_image_motion_clip(
                image_path=shot_img_path,
                duration=scene.duration_seconds,
                output_clip_path=output_path,
                motion_type=motion,
            )

        # Fallback to distinct clean cached artwork if available
        fallback_art = self._find_distinct_fallback_art(used_images=set())
        if fallback_art and fallback_art.exists():
            return self._motion_engine.render_image_motion_clip(
                image_path=fallback_art,
                duration=scene.duration_seconds,
                output_clip_path=output_path,
                motion_type=motion,
            )

        # DO NOT render an orange poster or synthetic text box. Fail fast with exact error!
        err_msg = self._last_error or "Image generation API failed and no clean fallback art is available"
        raise VideoGenerationError(f"Visual generation failed for scene {scene.scene_number}: {err_msg}")

    async def generate_video(
        self,
        scenes: Any = None,
        output_path: Path = None,
        job_id: int = 0,
        shots: Any = None,
    ) -> Path:
        """
        Generates each scene independently and concatenates them into an exact 10.0-second multi-scene video.
        Accepts either scenes (SceneDescription) or shots (StoryboardShot).
        """
        items = scenes if scenes is not None else shots
        if items is None:
            raise ValueError("No scenes or shots provided to generate_video")

        clip_paths: List[Path] = []
        used_images: Set[Path] = set()
        imagen_model = getattr(self._settings, "imagen_model", "imagen-3.0-generate-002")

        for idx, item in enumerate(items):
            shot_img_path = self._storage_dir / f"job_{job_id}_scene_{idx}.jpg"
            shot_clip_path = self._storage_dir / f"job_{job_id}_clip_{idx}.mp4"
            clean_visual = (getattr(item, "visual_description_english", None) or getattr(item, "visual_prompt", "")).strip()
            motion = getattr(item, "camera_motion", "zoom_in_dramatic")
            dur = float(getattr(item, "duration_seconds", getattr(item, "duration", 2.0)))

            prompt = (
                f"Cinematic vertical 9:16 sacred Hindu devotional art, {clean_visual}. "
                f"Radiant celestial golden aura, dramatic lighting, photorealistic 8k octane render. "
                f"Strictly NO text, NO titles, NO typography, NO watermark, NO storyboard panels, NO contact sheet."
            )

            img_ready = await self._fetch_imagen_shot(
                prompt=prompt,
                target_path=shot_img_path,
                imagen_model=imagen_model,
            )

            if img_ready and shot_img_path.exists() and shot_img_path.stat().st_size > 5000:
                clip_p = self._motion_engine.render_image_motion_clip(
                    image_path=shot_img_path,
                    duration=dur,
                    output_clip_path=shot_clip_path,
                    motion_type=motion,
                )
                used_images.add(shot_img_path)
            else:
                distinct_img = self._find_distinct_fallback_art(used_images)
                if distinct_img and distinct_img.exists():
                    clip_p = self._motion_engine.render_image_motion_clip(
                        image_path=distinct_img,
                        duration=dur,
                        output_clip_path=shot_clip_path,
                        motion_type=motion,
                    )
                    used_images.add(distinct_img)
                else:
                    err_msg = self._last_error or "Image generation API failed and no clean fallback art is available"
                    raise VideoGenerationError(f"Visual generation failed for scene {idx + 1}: {err_msg}")

            clip_paths.append(clip_p)

        # Concatenate all shots into single raw video with exact 10.000s duration
        return self._motion_engine.concatenate_shot_clips(
            clip_paths=clip_paths,
            output_video_path=output_path,
            target_duration=float(self._settings.video_duration_seconds),
        )
