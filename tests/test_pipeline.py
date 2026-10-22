"""
Tests: Video Pipeline (mocked stage progression and fault tolerance)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.models import JobStage, JobStatus, TopicCategory
from app.pipeline import VideoPipeline
from app.schemas import GeneratedScript, SceneDescription, ValidationResult


def make_dummy_script() -> GeneratedScript:
    return GeneratedScript(
        topic="भगवान राम का आदर्श चरित्र",
        topic_category=TopicCategory.DEITY,
        main_educational_takeaway="मर्यादा पुरुषोत्तम राम का जीवन धर्म और सदाचार का संदेश देता है",
        claim_type="traditional_interpretation",
        source_references=["वाल्मीकि रामायण"],
        hindi_narration="भगवान राम मर्यादा पुरुषोत्तम कहलाते हैं। उनका जीवन सत्य और धर्म की मिसाल है।",
        narration_word_count=13,
        scenes=[
            SceneDescription(
                scene_number=1,
                duration_seconds=5.0,
                visual_description_hindi="भगवान राम का भव्य रूप",
                visual_description_english="Lord Rama with bow and divine radiant smile",
                onscreen_text_hindi="मर्यादा पुरुषोत्तम",
                camera_motion="zoom",
                transition="cut",
            ),
            SceneDescription(
                scene_number=2,
                duration_seconds=5.0,
                visual_description_hindi="अयोध्या का भव्य दरबार",
                visual_description_english="Sacred golden palace of Ayodhya",
                onscreen_text_hindi="सत्य और धर्म",
                camera_motion="pan",
                transition="cut",
            ),
        ],
        video_title_hindi="श्री राम – मर्यादा पुरुषोत्तम #Shorts",
        video_description_hindi="भगवान राम का पावन जीवन",
        hashtags=["#Shorts", "#ShreeRam", "#Ayodhya"],
        content_verification_notes="Verified via Valmiki Ramayana",
        factual_concerns=[],
        estimated_narration_seconds=8.0,
    )


def make_settings():
    s = MagicMock()
    s.video_duration_seconds = 10
    s.auto_publish = False
    s.youtube_upload_enabled = False
    s.tts_speaking_rate = 1.1
    s.visual_generator = "free_motion"
    s.log_level = "INFO"
    return s


@pytest.mark.asyncio
async def test_pipeline_runs_all_stages_successfully(tmp_path):
    session = AsyncMock()
    session.add = MagicMock()
    settings = make_settings()
    gemini_client = MagicMock()
    quota_mgr = MagicMock()
    quota_mgr.record_event = AsyncMock()
    storage = MagicMock()

    pipeline = VideoPipeline(
        session=session,
        settings=settings,
        gemini_client=gemini_client,
        quota_manager=quota_mgr,
        storage=storage,
    )

    # Mock all internal sub-generators
    script = make_dummy_script()
    pipeline._script_gen.generate_script = AsyncMock(return_value=script)

    dummy_narration = tmp_path / "narration.aac"
    dummy_narration.write_bytes(b"dummy audio")
    pipeline._narration_gen.synthesize = AsyncMock(return_value=(dummy_narration, 8.5))

    dummy_video = tmp_path / "raw_video.mp4"
    dummy_video.write_bytes(b"dummy video")
    pipeline._video_gen._generate_free_motion_video = AsyncMock(return_value=dummy_video)
    pipeline._video_gen.submit_generation = AsyncMock(return_value="free_motion:raw_video.mp4")
    pipeline._video_gen.poll_until_complete = AsyncMock(return_value={"type": "free_motion", "path": str(dummy_video)})
    pipeline._video_gen.download_video = AsyncMock(return_value=dummy_video)

    def mock_render(*args, **kwargs):
        out_p = kwargs.get("output_path") or args[4]
        Path(out_p).write_bytes(b"dummy final video")
        return Path(out_p)

    pipeline._renderer.render_final_video = MagicMock(side_effect=mock_render)

    # Mock Job and Topic retrieval
    mock_job = MagicMock()
    mock_job.id = 99
    mock_job.topic_id = 1
    mock_job.stage = JobStage.TOPIC_SELECTED
    mock_job.status = JobStatus.PENDING
    mock_job.script_data = None

    mock_topic = MagicMock()
    mock_topic.id = 1
    mock_topic.topic_text = "भगवान राम का आदर्श चरित्र"
    mock_topic.category = TopicCategory.DEITY

    job_res = MagicMock()
    job_res.scalar_one_or_none.return_value = mock_job

    topic_res = MagicMock()
    topic_res.scalar_one_or_none.return_value = mock_topic

    session.execute.side_effect = [job_res, topic_res]

    from app.media.quality_gate import QualityCheckResult

    with (
        patch("app.pipeline.WORK_DIR", tmp_path),
        patch("app.topic_manager.TopicManager.get_all_topic_texts", new_callable=AsyncMock, return_value=[]),
        patch("app.media.quality_gate.QualityGate.inspect_video", return_value=QualityCheckResult(passed=True)),
    ):
        success = await pipeline.run_job(job_id=99)

    assert success is True
    pipeline._script_gen.generate_script.assert_called_once()
    pipeline._narration_gen.synthesize.assert_called_once()
    pipeline._renderer.render_final_video.assert_called_once()
