"""
Base Video Provider Interface & Capability Declarations
======================================================
Defines the standard contract for video generation adapters.
Enforces strict provider capability declarations:
- Text-to-image vs Text-to-video vs Image-to-video.
- Resolution, aspect ratio, and duration support.
- Asynchronous polling vs synchronous rendering.
- Pre-execution capability validation so image generators are never mistaken for video generators.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from app.schemas import SceneDescription


class VideoGenerationError(Exception):
    """Raised when video or visual generation fails unrecoverably."""
    pass


class ProviderCapabilityError(VideoGenerationError):
    """Raised when a provider is requested to perform an unsupported generation operation."""
    pass


@dataclass
class ProviderCapabilities:
    """
    Explicit capability manifest for a video/visual generation provider.
    """
    provider_name: str
    supports_text_to_video: bool = False
    supports_image_to_video: bool = False
    supports_text_to_image: bool = False
    supports_configurable_duration: bool = False
    supports_vertical_aspect_ratio: bool = True
    supports_async_polling: bool = False
    supports_downloadable_video: bool = True
    target_resolution: str = "1080x1920"
    target_fps: int = 30


class BaseVideoProvider(ABC):
    """
    Abstract contract for video generation providers.
    """

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return the explicit capability declaration for this provider."""
        pass

    @abstractmethod
    async def validate_readiness(self) -> tuple[bool, str]:
        """
        Validates whether the provider and configured model are currently accessible.
        Returns (is_ready: bool, message: str).
        """
        pass

    @abstractmethod
    async def generate_shot(
        self,
        scene: SceneDescription,
        output_path: Path,
        job_id: int,
    ) -> Path:
        """
        Generate a single video clip for an individual scene.
        Must produce a valid MP4 with exactly scene.duration_seconds at 1080x1920 30fps.
        """
        pass

    @abstractmethod
    async def generate_video(
        self,
        scenes: List[SceneDescription],
        output_path: Path,
        job_id: int,
    ) -> Path:
        """
        Generate and assemble all scenes into a complete multi-shot 10.0-second video.
        """
        pass
