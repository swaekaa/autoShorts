"""
Metadata Generator
==================
Generates video titles, descriptions, hashtags, and YouTube metadata
using Gemini. Separate from script generation for modularity.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.gemini.client import GeminiClient
from app.logging_config import get_logger
from app.schemas import GeneratedScript

logger = get_logger(__name__)


class MetadataGenerator:
    def __init__(self, client: GeminiClient):
        self._client = client

    async def generate_youtube_metadata(
        self,
        script: GeneratedScript,
    ) -> dict[str, Any]:
        """
        Generate or refine YouTube metadata from an existing script.
        Returns dict with title, description, tags, category_id, etc.
        """
        prompt = f"""
निम्नलिखित हिंदू शॉर्ट्स वीडियो के लिए YouTube मेटाडेटा तैयार करें:

विषय: {script.topic}
हिंदी वर्णन: {script.hindi_narration}
मुख्य शिक्षा: {script.main_educational_takeaway}

JSON में उत्तर दें:
{{
  "title": "आकर्षक हिंदी शीर्षक #Shorts (max 100 chars)",
  "description": "200-300 शब्दों में विवरण, शैक्षिक जानकारी के साथ",
  "tags": ["tag1", "tag2", ...],  // 15-30 tags, mix of Hindi and English
  "default_language": "hi",
  "category_id": 27
}}

नियम:
- शीर्षक में #Shorts अवश्य हो
- विवरण में स्रोत और अस्वीकरण शामिल करें
- tags में हिंदी और अंग्रेज़ी दोनों शामिल करें
"""

        text, _ = await self._client.generate_text(
            prompt=prompt,
            temperature=0.6,
            max_output_tokens=1024,
        )

        try:
            clean = text.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(
                    l for l in lines if not l.startswith("```")
                )
            metadata = json.loads(clean.strip())
        except Exception:
            # Fallback metadata from the script itself
            metadata = {
                "title": script.video_title_hindi[:100],
                "description": script.video_description_hindi[:5000],
                "tags": script.hashtags[:30],
                "default_language": "hi",
                "category_id": 27,
            }

        # Always ensure #Shorts is in title
        if "#Shorts" not in metadata.get("title", ""):
            metadata["title"] = metadata["title"].rstrip() + " #Shorts"

        # Truncate to YouTube limits
        metadata["title"] = metadata["title"][:100]
        metadata["description"] = metadata.get("description", "")[:5000]
        metadata["tags"] = metadata.get("tags", [])[:500]  # YouTube max 500 chars total in tags

        return metadata
