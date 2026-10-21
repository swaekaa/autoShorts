"""
Script Generator
================
Uses Gemini to produce structured, fact-checked Hindi scripts
for Hindu religion/mythology YouTube Shorts.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.gemini.client import GeminiClient
from app.logging_config import get_logger
from app.schemas import GeneratedScript, SceneDescription, TopicCategory

logger = get_logger(__name__)


SYSTEM_PROMPT = """आप एक विशेषज्ञ हिंदू धर्म और पौराणिक कथाओं के शिक्षक हैं।
आप YouTube Shorts के लिए 10-सेकंड के शैक्षिक वीडियो की स्क्रिप्ट लिखते हैं।

कठोर नियम:
1. शास्त्रों से उद्धरण केवल तभी दें जब वे वास्तविक हों
2. अध्याय/श्लोक संख्या कभी न बनाएं
3. पारंपरिक मान्यताओं को ऐतिहासिक तथ्य न बताएं
4. विवादित व्याख्याओं को सार्वभौमिक सत्य न बताएं
5. हिंदी वर्णन: केवल 18-25 शब्द (10 सेकंड में बोलने योग्य)
6. सामग्री शैक्षिक, सम्मानजनक और तथ्यात्मक हो

आपको JSON प्रारूप में उत्तर देना है।"""


SCRIPT_PROMPT_TEMPLATE = """
निम्नलिखित हिंदू धर्म विषय पर एक 10-सेकंड YouTube Short की स्क्रिप्ट तैयार करें:

**विषय:** {topic}
**श्रेणी:** {category}

**पहले से कवर किए गए विषय (दोहराएं नहीं):**
{existing_topics}

**आवश्यकताएं:**
- हिंदी वर्णन (hindi_narration): ठीक 18-25 शब्द (तेज़, स्पष्ट, ऊर्जावान, 10 सेकंड में बोलने योग्य)
- दृश्य (scenes): 3 दृश्य, प्रत्येक दृश्य का duration_seconds लगभग 3.3
- visual_description_english: प्रत्येक दृश्य के लिए विस्तृत अंग्रेजी प्रॉम्प्ट (divine devotional 9:16 art)
- video_title_hindi: आकर्षक हिंदी शीर्षक #Shorts के साथ
- hashtags: 10 प्रासंगिक हैशटैग

केवल निम्न JSON प्रारूप में उत्तर दें:
{{
  "video_title_hindi": "...",
  "hindi_narration": "...",
  "video_description_hindi": "...",
  "main_educational_takeaway": "...",
  "scenes": [
    {{
      "scene_number": 1,
      "visual_description_english": "...",
      "visual_description_hindi": "...",
      "onscreen_text_hindi": "...",
      "duration_seconds": 3.3
    }}
  ],
  "hashtags": ["#Shorts", "#Hinduism", "#SanatanDharma"]
}}
"""


class ScriptGenerator:
    def __init__(self, client: GeminiClient):
        self._client = client

    async def generate_script(
        self,
        topic: str,
        category: TopicCategory,
        existing_topics: list[str] | None = None,
    ) -> GeneratedScript:
        """
        Generate a structured script for the given topic.
        Returns a validated GeneratedScript object.
        """
        existing_str = "\n".join(
            f"- {t}" for t in (existing_topics or [])[:20]
        ) or "कोई नहीं"

        prompt = SCRIPT_PROMPT_TEMPLATE.format(
            topic=topic,
            category=category.value,
            existing_topics=existing_str,
        )

        logger.info(
            "Generating script",
            extra={"topic": topic[:80], "category": category.value},
        )

        text, usage = await self._client.generate_text(
            prompt=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=None,
            temperature=0.7,
            max_output_tokens=2048,
        )

        logger.debug("Raw Gemini response", extra={"length": len(text), "usage": usage})

        # Parse the structured JSON response
        script = self._parse_script_response(text, topic, category)

        # Validate narration word count
        words = script.hindi_narration.split()
        script.narration_word_count = len(words)
        script.estimated_narration_seconds = len(words) / 2.5  # ~2.5 words/sec in Hindi

        logger.info(
            "Script generated",
            extra={
                "topic": topic[:80],
                "word_count": script.narration_word_count,
                "estimated_seconds": script.estimated_narration_seconds,
                "scenes": len(script.scenes),
            },
        )
        return script

    def _parse_script_response(
        self, text: str, topic: str, category: TopicCategory
    ) -> GeneratedScript:
        """Parse and validate the JSON response from Gemini."""
        try:
            clean = text.strip()
            # Extract JSON between code fences if present
            if "```" in clean:
                for part in clean.split("```"):
                    cand = part.strip()
                    if cand.startswith("json"):
                        cand = cand[4:].strip()
                    if "{" in cand and "}" in cand:
                        clean = cand
                        break

            # Isolate outermost curly braces
            start = clean.find("{")
            end = clean.rfind("}")
            if start != -1 and end != -1:
                clean = clean[start:end + 1]

            data = json.loads(clean)

            # Normalize title
            title = data.get("video_title_hindi") or data.get("title") or f"{topic} #Shorts"
            data["video_title_hindi"] = title

            # Normalize narration
            narration = data.get("hindi_narration") or data.get("narration") or ""
            data["hindi_narration"] = narration

            # Normalize description & takeaways
            data.setdefault("video_description_hindi", f"{topic}\n\n#Shorts #HinduMythology #SanatanDharma")
            data.setdefault("main_educational_takeaway", f"{topic} का आध्यात्मिक एवं सांस्कृतिक महत्व")
            data.setdefault("claim_type", "traditional_interpretation")

            # Normalize scenes
            raw_scenes = data.get("scenes") or []
            if not isinstance(raw_scenes, list) or len(raw_scenes) == 0:
                raw_scenes = [{"scene_number": 1, "visual_description": topic}]

            clean_scenes = []
            default_dur = round(10.0 / max(1, len(raw_scenes)), 1)
            for i, sc in enumerate(raw_scenes, 1):
                if not isinstance(sc, dict):
                    sc = {}
                sc_num = sc.get("scene_number", i)
                vis_desc = sc.get("visual_description_hindi") or sc.get("visual_description") or sc.get("description") or topic
                vis_en = sc.get("visual_description_english") or sc.get("visual_description") or topic
                onscreen = sc.get("onscreen_text_hindi") or sc.get("text") or sc.get("title") or topic

                dur = sc.get("duration_seconds")
                if dur is None:
                    ts = str(sc.get("timestamp", ""))
                    if "-" in ts:
                        try:
                            parts = ts.split("-")
                            dur = abs(float(parts[1].strip().split(":")[-1]) - float(parts[0].strip().split(":")[-1]))
                        except Exception:
                            dur = default_dur
                    else:
                        dur = default_dur

                clean_scenes.append({
                    "scene_number": sc_num,
                    "duration_seconds": float(dur or default_dur),
                    "visual_description_hindi": str(vis_desc),
                    "visual_description_english": str(vis_en),
                    "onscreen_text_hindi": str(onscreen),
                    "camera_motion": sc.get("camera_motion", "slow zoom in"),
                    "transition": sc.get("transition", "cut"),
                })
            data["scenes"] = clean_scenes

            # Defaults for other fields
            data.setdefault("topic", topic)
            data.setdefault("topic_category", category.value)
            data.setdefault("source_references", [])
            data.setdefault("factual_concerns", [])
            data.setdefault("narration_word_count", len(narration.split()))
            data.setdefault("estimated_narration_seconds", len(narration.split()) / 2.5)
            data.setdefault("content_verification_notes", "")
            data.setdefault("hashtags", ["#Shorts", "#HinduMythology", "#Hinduism"])

            # Ensure #Shorts is in hashtags
            if "#Shorts" not in data["hashtags"] and "#shorts" not in data["hashtags"]:
                data["hashtags"].insert(0, "#Shorts")

            return GeneratedScript.model_validate(data)

        except (json.JSONDecodeError, Exception) as exc:
            logger.error(
                "Failed to parse script response",
                extra={"error": str(exc), "raw_text": text[:500]},
            )
            raise ValueError(f"Script parsing failed: {exc}") from exc

    async def generate_additional_topics(
        self,
        existing_topics: list[str],
        count: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Ask Gemini to suggest new unique Hindu mythology topics.
        Returns list of {"text": str, "category": str} dicts.
        """
        existing_str = "\n".join(f"- {t}" for t in existing_topics[:30])
        prompt = f"""
हिंदू धर्म और पौराणिक कथाओं पर {count} नए, अनोखे YouTube Short विषय सुझाएं।
ये पहले से मौजूद विषयों से अलग हों:
{existing_str}

JSON array में उत्तर दें, प्रत्येक item में:
- "text": हिंदी में विषय (संक्षिप्त, 5-12 शब्द)
- "category": एक श्रेणी [deity, mythology, scripture, festival, philosophy, ritual, temple, symbolism, tradition, historical, regional]

केवल JSON array, कोई अन्य text नहीं।
"""
        text, _ = await self._client.generate_text(
            prompt=prompt,
            temperature=0.9,
            max_output_tokens=1024,
        )

        try:
            # Strip markdown code fences if present
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            topics = json.loads(clean.strip())
            return [t for t in topics if isinstance(t, dict) and "text" in t]
        except Exception as exc:
            logger.warning("Topic generation parse error", extra={"error": str(exc)})
            return []
