"""
Tests: Video Generator (mocked Google GenAI SDK, Imagen 3, Veo, and procedural visual fallback)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models import TopicCategory
from app.schemas import GeneratedScript, SceneDescription
from app.video.generator import VideoGenerationError, VideoGenerator


def make_dummy_script() -> GeneratedScript:
    return GeneratedScript(
        topic="भगवान शिव का नटराज स्वरूप",
        topic_category=TopicCategory.DEITY,
        main_educational_takeaway="नटराज स्वरूप सृष्टि, स्थिति और संहार का प्रतीक है",
        claim_type="traditional_interpretation",
        source_references=["शिव पुराण"],
        hindi_narration="भगवान शिव का नटराज स्वरूप ब्रह्मांडीय नृत्य का दिव्य प्रतीक है।",
        narration_word_count=10,
        scenes=[
            SceneDescription(
                scene_number=1,
                duration_seconds=5.0,
                visual_description_hindi="भगवान शिव का नटराज रूप",
                visual_description_english="Lord Shiva as Nataraja surrounded by cosmic fire halo",
                onscreen_text_hindi="नटराज शिव",
                camera_motion="zoom in",
                transition="fade",
            ),
            SceneDescription(
                scene_number=2,
                duration_seconds=5.0,
                visual_description_hindi="दिव्य अग्नि चक्र",
                visual_description_english="Sacred circle of cosmic flame in dark celestial void",
                onscreen_text_hindi="ब्रह्मांडीय नृत्य",
                camera_motion="pan",
                transition="cut",
            ),
        ],
        video_title_hindi="शिव नटराज का दिव्य रहस्य #Shorts",
        video_description_hindi="भगवान शिव के नटराज स्वरूप का अर्थ",
        hashtags=["#Shorts", "#Shiva", "#Nataraja"],
        content_verification_notes="Verified via Shiva Purana",
        factual_concerns=[],
        estimated_narration_seconds=8.0,
    )


def make_settings(
    visual_generator="free_motion",
    imagen_model="imagen-3.0-generate-002",
    enable_pollinations_fallback=False,
):
    s = MagicMock()
    s.visual_generator = visual_generator
    s.gemini_video_model = "veo-3.1-fast-generate-preview"
    s.imagen_model = imagen_model
    s.enable_pollinations_fallback = enable_pollinations_fallback
    return s


@pytest.mark.asyncio
async def test_fetch_scene_image_success_via_google_imagen(tmp_path):
    # Mock Google GenAI client models.generate_images
    mock_genai_client = MagicMock()
    mock_img_obj = MagicMock()
    mock_img_obj.image.image_bytes = b"\xff\xd8\xff\xe0" + b"0" * 6000  # valid JPEG header fake
    mock_result = MagicMock()
    mock_result.generated_images = [mock_img_obj]
    mock_genai_client.models.generate_images.return_value = mock_result

    client = MagicMock()
    client._client = mock_genai_client

    quota_mgr = MagicMock()
    settings = make_settings()

    generator = VideoGenerator(
        client=client,
        quota_manager=quota_mgr,
        settings=settings,
        storage_dir=str(tmp_path),
    )

    target_path = tmp_path / "scene_0.jpg"
    success, api_available = await generator._fetch_scene_image(
        prompt="Lord Shiva Nataraja",
        target_path=target_path,
        seed=100,
    )

    assert success is True
    assert api_available is True
    assert target_path.exists()
    assert target_path.stat().st_size > 5000
    mock_genai_client.models.generate_images.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_scene_image_quota_exhausted_breaks_circuit(tmp_path):
    mock_genai_client = MagicMock()
    mock_genai_client.models.generate_images.side_effect = Exception("429 RESOURCE_EXHAUSTED: quota exceeded")

    client = MagicMock()
    client._client = mock_genai_client

    quota_mgr = MagicMock()
    settings = make_settings(enable_pollinations_fallback=False)

    generator = VideoGenerator(
        client=client,
        quota_manager=quota_mgr,
        settings=settings,
        storage_dir=str(tmp_path),
    )

    target_path = tmp_path / "scene_0.jpg"
    success, api_available = await generator._fetch_scene_image(
        prompt="Lord Shiva Nataraja",
        target_path=target_path,
        seed=100,
    )

    # Should fail cleanly without throwing, and report api_available=False
    assert success is False
    assert api_available is False
    assert not target_path.exists()


@pytest.mark.asyncio
async def test_pollinations_fallback_disabled_by_default(tmp_path):
    # When GenAI throws an error and enable_pollinations_fallback is False, no HTTP client is contacted
    mock_genai_client = MagicMock()
    mock_genai_client.models.generate_images.side_effect = Exception("Service unavailable")

    client = MagicMock()
    client._client = mock_genai_client

    quota_mgr = MagicMock()
    settings = make_settings(enable_pollinations_fallback=False)

    generator = VideoGenerator(
        client=client,
        quota_manager=quota_mgr,
        settings=settings,
        storage_dir=str(tmp_path),
    )

    target_path = tmp_path / "scene_0.jpg"
    with patch("httpx.AsyncClient") as mock_httpx:
        success, _ = await generator._fetch_scene_image(
            prompt="Lord Shiva Nataraja",
            target_path=target_path,
            seed=100,
        )
        assert success is False
        mock_httpx.assert_not_called()


@pytest.mark.asyncio
async def test_veo_submission_when_configured(tmp_path):
    client = MagicMock()
    mock_operation = MagicMock()
    mock_operation.name = "operations/veo-job-12345"
    client.submit_video_generation.return_value = mock_operation

    quota_mgr = MagicMock()
    quota_mgr.can_generate = AsyncMock(return_value=True)
    quota_mgr.record_event = AsyncMock()

    settings = make_settings(visual_generator="veo")

    generator = VideoGenerator(
        client=client,
        quota_manager=quota_mgr,
        settings=settings,
        storage_dir=str(tmp_path),
    )

    script = make_dummy_script()
    op_id = await generator.submit_generation(script=script, job_id=42)

    assert op_id == "operations/veo-job-12345"
    client.submit_video_generation.assert_called_once()


@pytest.mark.asyncio
async def test_veo_submission_fails_when_quota_exhausted(tmp_path):
    client = MagicMock()
    quota_mgr = MagicMock()
    quota_mgr.can_generate = AsyncMock(return_value=False)
    quota_mgr.get_cooldown_remaining = AsyncMock(return_value=120)
    quota_mgr.record_event = AsyncMock()

    settings = make_settings(visual_generator="veo")

    generator = VideoGenerator(
        client=client,
        quota_manager=quota_mgr,
        settings=settings,
        storage_dir=str(tmp_path),
    )

    script = make_dummy_script()
    with pytest.raises(VideoGenerationError, match="Video generation quota unavailable"):
        await generator.submit_generation(script=script, job_id=42)


@pytest.mark.asyncio
async def test_generate_free_motion_video_plans_storyboard_and_calls_provider(tmp_path):
    client = MagicMock()
    quota_mgr = MagicMock()
    settings = make_settings(visual_generator="free_motion")

    generator = VideoGenerator(
        client=client,
        quota_manager=quota_mgr,
        settings=settings,
        storage_dir=str(tmp_path),
    )

    script = make_dummy_script()
    mock_raw_output = tmp_path / "job_42_raw_video.mp4"
    mock_raw_output.write_bytes(b"fake 10s video")

    with patch("app.video.providers.imagen_motion_provider.GoogleImagenMotionProvider.generate_video", new_callable=AsyncMock) as mock_gen_video:
        mock_gen_video.return_value = mock_raw_output
        res = await generator._generate_free_motion_video(script=script, job_id=42)

        assert res == mock_raw_output
        mock_gen_video.assert_called_once()
        args, kwargs = mock_gen_video.call_args
        # Verify storyboard was planned with 10.0s total duration
        shots = kwargs.get("shots") or args[0]
        assert len(shots) >= 2
        assert abs(sum(s.duration for s in shots) - 10.0) < 0.05

