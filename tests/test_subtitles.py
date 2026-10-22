"""
Tests: Subtitle Generator (Devanagari ASS generation)
"""

from pathlib import Path
import pytest

from app.media.subtitles import generate_subtitles, _format_ass_time
from app.models import TopicCategory
from app.schemas import GeneratedScript, SceneDescription


def make_dummy_script() -> GeneratedScript:
    return GeneratedScript(
        topic="भगवान विष्णु के दशावतार",
        topic_category=TopicCategory.DEITY,
        main_educational_takeaway="विष्णु जी धर्म की रक्षा हेतु अवतार लेते हैं",
        claim_type="traditional_interpretation",
        source_references=["विष्णु पुराण"],
        hindi_narration="धर्म की रक्षा के लिए भगवान विष्णु ने विभिन्न कालों में दस प्रमुख अवतार लिए।",
        narration_word_count=13,
        scenes=[
            SceneDescription(
                scene_number=1,
                duration_seconds=5.0,
                visual_description_hindi="मत्स्य अवतार",
                visual_description_english="Matsya avatar of Vishnu",
                onscreen_text_hindi="मत्स्य अवतार",
                camera_motion="static",
                transition="cut",
            ),
            SceneDescription(
                scene_number=2,
                duration_seconds=5.0,
                visual_description_hindi="कूर्म अवतार",
                visual_description_english="Kurma avatar supporting Mandara mountain",
                onscreen_text_hindi="कूर्म अवतार",
                camera_motion="static",
                transition="cut",
            ),
        ],
        video_title_hindi="विष्णु के दशावतार #Shorts",
        video_description_hindi="दशावतार की कथा",
        hashtags=["#Shorts", "#Vishnu"],
        content_verification_notes="Verified",
        factual_concerns=[],
        estimated_narration_seconds=8.0,
    )


def test_format_ass_time():
    assert _format_ass_time(0.0) == "0:00:00.00"
    assert _format_ass_time(5.5) == "0:00:05.50"
    assert _format_ass_time(65.25) == "0:01:05.25"


def test_generate_subtitles_creates_valid_ass_file(tmp_path):
    output_path = tmp_path / "test_subtitles.ass"
    script = make_dummy_script()

    result_path = generate_subtitles(script=script, output_path=output_path, total_duration=10.0)
    assert result_path.exists()

    content = result_path.read_text(encoding="utf-8")
    assert "[Script Info]" in content
    assert "[V4+ Styles]" in content
    assert "[Events]" in content
    assert "मत्स्य अवतार" in content
    assert "कूर्म अवतार" in content
