"""
Tests: Video Provider Capabilities and Static Image Rejection
=============================================================
Verifies:
1. Provider capability declarations (Text-to-Video vs Animated Image).
2. Image generators cannot be silently treated as true video models.
3. Failures in visual generation raise exceptions instead of producing synthetic text posters.
4. QualityGate rejects static single-frame videos or static posters.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.media.quality_gate import QualityGate
from app.schemas import SceneDescription
from app.video.generator import VideoGenerationError, VideoGenerator
from app.video.providers.base import ProviderCapabilities, ProviderCapabilityError
from app.video.providers.imagen_motion_provider import GoogleImagenMotionProvider
from app.video.providers.veo_provider import VeoVideoProvider


def make_dummy_settings(visual_generator="free_motion"):
    s = MagicMock()
    s.visual_generator = visual_generator
    s.gemini_video_model = "veo-2.0-generate-001"
    s.imagen_model = "imagen-3.0-generate-002"
    s.video_duration_seconds = 10
    s.video_width = 1080
    s.video_height = 1920
    s.video_fps = 30
    return s


def test_veo_provider_capabilities():
    client = MagicMock()
    settings = make_dummy_settings("veo")
    provider = VeoVideoProvider(client, settings, Path("storage/test"))
    caps = provider.get_capabilities()

    assert caps.provider_name == "google_veo"
    assert caps.supports_text_to_video is True
    assert caps.supports_text_to_image is False
    assert caps.supports_downloadable_video is True


def test_imagen_provider_capabilities():
    client = MagicMock()
    settings = make_dummy_settings("free_motion")
    provider = GoogleImagenMotionProvider(client, settings, Path("storage/test"))
    caps = provider.get_capabilities()

    assert caps.provider_name == "google_imagen_motion"
    assert caps.supports_text_to_video is False
    assert caps.supports_text_to_image is True
    assert caps.supports_downloadable_video is True


@pytest.mark.asyncio
async def test_imagen_failure_raises_error_without_poster_fallback(tmp_path):
    """
    Ensures that when image generation fails, the provider does NOT fall back
    to an orange text box or poster, but instead raises VideoGenerationError.
    """
    client = MagicMock()
    client._client.models.generate_images.side_effect = RuntimeError("Quota exhausted or 403 Forbidden")
    client._client.models.generate_content.side_effect = RuntimeError("Quota exhausted or 403 Forbidden")
    settings = make_dummy_settings("free_motion")

    provider = GoogleImagenMotionProvider(client, settings, tmp_path)

    scene = SceneDescription(
        scene_number=1,
        duration_seconds=2.0,
        visual_description_english="Goddess Durga on lion",
    )

    with pytest.raises(VideoGenerationError) as exc_info:
        await provider.generate_shot(scene, tmp_path / "shot_0.mp4", job_id=99)

    assert "Visual generation failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_quality_gate_rejects_static_video(tmp_path):
    """
    Verifies that the QualityGate rejects a video if all sampled frames are identical (static picture).
    """
    settings = make_dummy_settings()
    gate = QualityGate(settings)

    video_file = tmp_path / "static_poster.mp4"
    video_file.write_bytes(b"dummy" * 30000)

    # Mock _probe_metadata to return valid format
    valid_probe = {
        "format": {"duration": "10.00"},
        "streams": [
            {"codec_type": "video", "width": 1080, "height": 1920, "r_frame_rate": "30/1", "nb_frames": 300},
            {"codec_type": "audio", "duration": "10.00"},
        ],
    }

    # Simulate _verify_scene_diversity returning False (static frames detected)
    with (
        patch.object(gate, "_probe_metadata", return_value=valid_probe),
        patch("subprocess.run", return_value=MagicMock(returncode=0)),
        patch.object(gate, "_verify_scene_diversity", return_value=False),
    ):
        result = gate.inspect_video(video_file)

    assert result.passed is False
    assert any("Static image or lack of scene diversity detected" in e for e in result.errors)
