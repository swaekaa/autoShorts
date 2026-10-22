"""
Tests: Scene Planner Module
"""

import pytest
from app.models import TopicCategory
from app.schemas import GeneratedScript, SceneDescription
from app.video.scene_planner import ScenePlanner


def make_dummy_script(scene_count: int = 3) -> GeneratedScript:
    scenes = [
        SceneDescription(
            scene_number=i + 1,
            duration_seconds=10.0 / scene_count,
            visual_description_hindi=f"दृश्य {i+1}",
            visual_description_english=f"Scene {i+1} description",
            onscreen_text_hindi=f"पाठ {i+1}",
            camera_motion="zoom",
            transition="cut",
        )
        for i in range(scene_count)
    ]
    return GeneratedScript(
        topic="भगवान गणेश का विघ्नहर्ता स्वरूप",
        topic_category=TopicCategory.DEITY,
        main_educational_takeaway="विघ्नहर्ता गणेश",
        claim_type="traditional_interpretation",
        source_references=["गणेश पुराण"],
        hindi_narration="भगवान गणेश सभी विघ्नों को हरने वाले हैं।",
        narration_word_count=8,
        scenes=scenes,
        video_title_hindi="गणेश महिमा #Shorts",
        video_description_hindi="विवरण",
        hashtags=["#Shorts"],
        content_verification_notes="Verified",
        factual_concerns=[],
        estimated_narration_seconds=8.0,
    )


def test_storyboard_exact_10_seconds_3_scenes():
    planner = ScenePlanner()
    script = make_dummy_script(scene_count=3)
    storyboard = planner.create_storyboard(script)

    assert len(storyboard) == 3
    total_dur = sum(s.duration for s in storyboard)
    assert abs(total_dur - 10.0) < 1e-4
    assert storyboard[-1].end_time == 10.0


def test_storyboard_exact_10_seconds_5_scenes():
    planner = ScenePlanner()
    script = make_dummy_script(scene_count=5)
    storyboard = planner.create_storyboard(script)

    assert len(storyboard) == 5
    total_dur = sum(s.duration for s in storyboard)
    assert abs(total_dur - 10.0) < 1e-4
    assert storyboard[-1].end_time == 10.0


def test_storyboard_camera_motions_vary():
    planner = ScenePlanner()
    script = make_dummy_script(scene_count=5)
    storyboard = planner.create_storyboard(script)

    motions = [s.camera_motion for s in storyboard]
    # Verify that motions are diverse, not all identical
    assert len(set(motions)) >= 3
