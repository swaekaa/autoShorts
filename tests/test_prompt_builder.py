"""
Tests: Prompt Builder Module
"""

from app.video.prompt_builder import PromptBuilder


def test_identify_deity():
    assert PromptBuilder.identify_deity("शिव तांडव स्तोत्र") == "shiva"
    assert PromptBuilder.identify_deity("Lord Ganesha Vignaharta") == "ganesha"
    assert PromptBuilder.identify_deity("कृष्ण लीला माखन चोरी") == "krishna"
    assert PromptBuilder.identify_deity("मर्यादा पुरुषोत्तम श्री राम") == "rama"
    assert PromptBuilder.identify_deity("माँ दुर्गा महिषासुरमर्दिनी") == "durga"
    assert PromptBuilder.identify_deity("बजरंगबली हनुमान संजीवनी") == "hanuman"


def test_build_shot_prompt_contains_vertical_and_negative_rules():
    prompt = PromptBuilder.build_shot_prompt(
        topic="भगवान शिव का नटराज स्वरूप",
        shot_type="mythological_climax",
        scene_description="Lord Shiva performing cosmic Tandava dance in ring of fire",
        shot_index=2,
    )

    assert "vertical 9:16" in prompt.lower()
    assert "no watermarks" in prompt.lower()
    assert "no logos" in prompt.lower()
    assert "no text" in prompt.lower()
    assert "trishula" in prompt.lower() or "shiva" in prompt.lower()
