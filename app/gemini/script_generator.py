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
- हिंदी वर्णन: 18-25 शब्द (तेज़, स्पष्ट, ऊर्जावान)
- दृश्य: 3-5 दृश्य, कुल 10 सेकंड
- वीडियो शीर्षक: आकर्षक हिंदी शीर्षक #Shorts के साथ
- हैशटैग: 10-15 प्रासंगिक हैशटैग
- तथ्यात्मक सटीकता: स्रोत और सत्यापन नोट्स शामिल करें

JSON प्रारूप में उत्तर दें जो इस schema से मेल खाता हो।
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

        # Use GeneratedScript as the response schema for structured output
        text, usage = await self._client.generate_text(
            prompt=prompt,
            system_instruction=SYSTEM_PROMPT,
            response_schema=GeneratedScript,
            temperature=0.8,
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
            # Ensure required fields have defaults if missing
            data.setdefault("topic", topic)
            data.setdefault("topic_category", category.value)
            data.setdefault("source_references", [])
            data.setdefault("factual_concerns", [])
            data.setdefault("narration_word_count", 0)
            data.setdefault("estimated_narration_seconds", 0.0)
            data.setdefault("content_verification_notes", "")
            data.setdefault("hashtags", ["#Shorts", "#HinduMythology", "#Hinduism"])

            # Ensure #Shorts is always included
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
