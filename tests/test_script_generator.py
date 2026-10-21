"""
Tests: Script Generator (mocked Gemini)
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.gemini.script_generator import ScriptGenerator
from app.models import TopicCategory
from app.schemas import GeneratedScript, SceneDescription


def make_mock_client(response_json: dict):
    client = MagicMock()
    client.generate_text = AsyncMock(
        return_value=(json.dumps(response_json), {"total_token_count": 500})
    )
    return client


VALID_SCRIPT_RESPONSE = {
    "topic": "भगवान गणेश का विघ्नहर्ता स्वरूप",
    "topic_category": "deity",
    "main_educational_takeaway": "गणेश जी सभी विघ्नों को हरते हैं",
    "claim_type": "traditional_interpretation",
    "source_references": ["गणेश पुराण"],
    "hindi_narration": "भगवान गणेश को विघ्नहर्ता कहते हैं। वे हर काम की शुरुआत में पूजे जाते हैं। उनकी पूजा से सभी बाधाएं दूर होती हैं।",
    "narration_word_count": 22,
    "scenes": [
        {
            "scene_number": 1,
            "duration_seconds": 3.0,
            "visual_description_hindi": "गणेश जी का दिव्य रूप",
            "visual_description_english": "Divine form of Lord Ganesha with golden halo",
            "onscreen_text_hindi": "विघ्नहर्ता गणेश",
            "camera_motion": "slow zoom in",
            "transition": "fade",
        },
        {
            "scene_number": 2,
            "duration_seconds": 4.0,
            "visual_description_hindi": "भक्त गणेश की पूजा करते हैं",
            "visual_description_english": "Devotees worshipping Ganesha idol",
            "onscreen_text_hindi": "हर शुभ कार्य में पहले गणेश",
            "camera_motion": "pan right",
            "transition": "cut",
        },
        {
            "scene_number": 3,
            "duration_seconds": 3.0,
            "visual_description_hindi": "बाधाएं दूर होती हैं",
            "visual_description_english": "Path clearing with divine light",
            "onscreen_text_hindi": "जय गणेश!",
            "camera_motion": "static",
            "transition": "cut",
        },
    ],
    "video_title_hindi": "भगवान गणेश – विघ्नहर्ता की कथा #Shorts",
    "video_description_hindi": "गणेश जी के बारे में जानें",
    "hashtags": ["#Shorts", "#Ganesha", "#HinduMythology", "#हिंदू", "#गणेश"],
    "content_verification_notes": "Based on traditional Hindu worship practices",
    "factual_concerns": [],
    "estimated_narration_seconds": 8.8,
}


@pytest.mark.asyncio
async def test_generate_script_returns_valid_object():
    client = make_mock_client(VALID_SCRIPT_RESPONSE)
    gen = ScriptGenerator(client)
    script = await gen.generate_script(
        topic="भगवान गणेश का विघ्नहर्ता स्वरूप",
        category=TopicCategory.DEITY,
        existing_topics=[],
    )
    assert isinstance(script, GeneratedScript)
    assert script.topic == "भगवान गणेश का विघ्नहर्ता स्वरूप"
    assert script.topic_category == TopicCategory.DEITY
    assert len(script.scenes) == 3
    assert "#Shorts" in script.hashtags


@pytest.mark.asyncio
async def test_generate_script_always_includes_shorts_hashtag():
    response = dict(VALID_SCRIPT_RESPONSE)
    response["hashtags"] = ["#Ganesha", "#Hindu"]  # No #Shorts
    client = make_mock_client(response)
    gen = ScriptGenerator(client)
    script = await gen.generate_script("test", TopicCategory.DEITY)
    assert "#Shorts" in script.hashtags


@pytest.mark.asyncio
async def test_generate_script_handles_invalid_json():
    client = MagicMock()
    client.generate_text = AsyncMock(return_value=("INVALID JSON {{{", {}))
    gen = ScriptGenerator(client)
    with pytest.raises(ValueError, match="Script parsing failed"):
        await gen.generate_script("test", TopicCategory.DEITY)


@pytest.mark.asyncio
async def test_narration_word_count_computed():
    client = make_mock_client(VALID_SCRIPT_RESPONSE)
    gen = ScriptGenerator(client)
    script = await gen.generate_script("test", TopicCategory.DEITY)
    assert script.narration_word_count > 0
    words = script.hindi_narration.split()
    assert script.narration_word_count == len(words)


@pytest.mark.asyncio
async def test_generate_additional_topics_returns_list():
    topics_response = [
        {"text": "भगवान कृष्ण की बाल लीला", "category": "deity"},
        {"text": "दुर्गा माँ का नवरात्रि महत्व", "category": "festival"},
    ]
    client = MagicMock()
    client.generate_text = AsyncMock(
        return_value=(json.dumps(topics_response), {})
    )
    gen = ScriptGenerator(client)
    result = await gen.generate_additional_topics(["existing topic"])
    assert len(result) == 2
    assert result[0]["text"] == "भगवान कृष्ण की बाल लीला"
