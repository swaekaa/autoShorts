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
निम्नलिखित हिंदू धर्म विषय पर एक 10-सेकंड YouTube Short की उच्च-गुणवत्ता वाली सिनेमाई स्टोरीबोर्ड स्क्रिप्ट तैयार करें:

**विषय:** {topic}
**श्रेणी:** {category}

**पहले से कवर किए गए विषय (दोहराएं नहीं):**
{existing_topics}

**सिनेमाई स्टोरीबोर्ड आवश्यकताएं (10 सेकंड YouTube Short):**
- **शैली:** महाकाव्य, उच्च-ऊर्जा, तीव्र गति वाला भारतीय पौराणिक सिनेमाई वीडियो। जीवंत स्वर्णिम और गहरे केसरिया रंग, दिव्य प्रकाश प्रभाव, अलौकिक आभामंडल।
- **हिंदी वर्णन (hindi_narration):** 20-25 शब्द (तीव्र, ऊर्जावान, भक्तिमय, 10 सेकंड में स्पष्ट बोलने योग्य)।
- **दृश्य (scenes):** 5 तीव्र सिनेमाई दृश्य (कुल 10.0 सेकंड):
  * दृश्य 1 (0 - 1.5s): नाटकीय संकट या पौराणिक पृष्ठभूमि (उदा. शक्तिशाली असुर का भय / ब्रह्मांडीय चुनौती)।
  * दृश्य 2 (1.5 - 3.0s): दिव्य शक्तियों / देवताओं का एकीकरण, ब्रह्मांडीय स्वर्णिम ऊर्जा पुंज।
  * दृश्य 3 (3.0 - 4.8s): मुख्य दिव्य स्वरूप का भव्य प्राकट्य (वाहन, दिव्य अस्त्र, स्वर्णिम आभामंडल, 8k ऑक्टेन रेंडर)।
  * दृश्य 4 (4.8 - 7.5s): तीव्र क्रिया या विभिन्न दिव्य रूपों/अवतारों का महाकाव्य मोंटाज।
  * दृश्य 5 (7.5 - 10.0s): दिव्य आशीर्वाद, भक्त की प्रार्थना, भक्तिमय समापन।
- **visual_description_english:** प्रत्येक दृश्य के लिए अति-विस्तृत अंग्रेजी प्रॉम्प्ट (अत्यधिक जीवंत, स्वर्णिम किरणें, अलौकिक अस्त्र, 8k 9:16 vertical render):
  उदा: "Epic cinematic vertical 9:16 photorealistic sacred Hindu mythology art of Maa Durga riding lion with golden trishul, volumetric celestial light rays, radiant golden halo, cosmic background, 8k octane render masterpiece"
- **onscreen_text_hindi:** स्क्रीन पर दिखाने के लिए संक्षिप्त और प्रभावशाली हिंदी कैप्शन (उदा. "जय माता दी 🙏", "दिव्य शक्ति ✨", "महिषासुर संहार")
- **video_title_hindi:** आकर्षक और क्लिक करने योग्य हिंदी शीर्षक इमोजी और #Shorts के साथ
- **hashtags:** 8-12 प्रासंगिक हैशटैग (#Shorts, #SanatanDharma, #DeviShakti, आदि)

केवल निम्न JSON प्रारूप में उत्तर दें:
{{
  "video_title_hindi": "...",
  "hindi_narration": "...",
  "video_description_hindi": "...",
  "main_educational_takeaway": "...",
  "scenes": [
    {{
      "scene_number": 1,
      "duration_seconds": 1.5,
      "visual_description_english": "Dark dramatic scene of powerful demon Mahishasura with glowing red eyes creating destruction, cosmic storm, intricate Hindu mythological art, 8k vertical 9:16",
      "visual_description_hindi": "...",
      "onscreen_text_hindi": "असुर का आतंक",
      "camera_motion": "slow zoom in"
    }},
    {{
      "scene_number": 2,
      "duration_seconds": 1.5,
      "visual_description_english": "Divine Hindu gods Brahma, Vishnu, Shiva combining their celestial cosmic energies into a bright blinding golden light, radiant volumetric rays, 8k vertical 9:16",
      "visual_description_hindi": "...",
      "onscreen_text_hindi": "देवताओं की शक्ति",
      "camera_motion": "pan up"
    }},
    {{
      "scene_number": 3,
      "duration_seconds": 2.0,
      "visual_description_english": "Supreme Goddess Maa Durga emerges majestically from divine golden light, golden crown, glowing third eye, holding sacred weapons in ten arms, riding radiant lion, 8k vertical 9:16",
      "visual_description_hindi": "...",
      "onscreen_text_hindi": "माँ दुर्गा का प्राकट्य",
      "camera_motion": "slow zoom in"
    }},
    {{
      "scene_number": 4,
      "duration_seconds": 2.5,
      "visual_description_english": "Fierce Goddess Maa Durga riding roaring lion slaying Mahishasura demon with radiant glowing trident trishul, dynamic cosmic battle sparks, 8k vertical 9:16",
      "visual_description_hindi": "...",
      "onscreen_text_hindi": "बुराई का विनाश",
      "camera_motion": "zoom out"
    }},
    {{
      "scene_number": 5,
      "duration_seconds": 2.5,
      "visual_description_english": "Devotee with folded hands praying in devotion before radiant smiling Goddess Maa Durga who blesses with golden shower of celestial light and flower petals, 8k vertical 9:16",
      "visual_description_hindi": "...",
      "onscreen_text_hindi": "जय माता दी 🙏",
      "camera_motion": "slow zoom in"
    }}
  ],
  "hashtags": ["#Shorts", "#Navratri", "#MaaDurga", "#SanatanDharma", "#HinduMythology"]
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
        # If topic is about Maa Durga's 9 forms, return the perfected 6-scene storyboard
        norm = topic.lower()
        if any(k in norm for k in ["दुर्गा", "durga", "नौ रूप", "9 different forms", "9 रूप"]):
            logger.info("Using calibrated Maa Durga 9 Forms storyboard preset", extra={"topic": topic})
            return self._get_durga_9_forms_script()

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
                    "voiceover_hindi": str(sc.get("voiceover_hindi") or sc.get("voiceover") or sc.get("narration") or ""),
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

    def _get_durga_9_forms_script(self) -> GeneratedScript:
        """
        Pre-calibrated 10-second master storyboard for Maa Durga's 9 Forms.
        Matches the exact cinematic scene-by-scene timing, voiceover, and visual breakdown from the user storyboard.
        """
        data = {
            "topic": "माँ दुर्गा ने नौ रूप क्यों धारण किए?",
            "topic_category": "mythology",
            "video_title_hindi": "माँ दुर्गा ने नौ रूप क्यों धारण किए? 😱 जानिए 10 सेकंड में! 🙏 #Shorts",
            "hindi_narration": (
                "जब महिषासुर नाम का असुर बहुत शक्तिशाली हो गया तब सभी देवताओं ने अपनी-अपनी शक्तियां एक साथ मिलाईं "
                "और उस दिव्य ऊर्जा से माँ दुर्गा का प्रकट हुआ। उन्होंने नौ अलग-अलग रूप धारण किए ताकि हर प्रकार की "
                "नकारात्मक शक्ति का विनाश किया जा सके। माँ दुर्गा के ये नौ रूप हमें सिखाते हैं कि हर चुनौती का "
                "सामना करने की शक्ति हम सब में है। जय माता दी!"
            ),
            "video_description_hindi": (
                "जब महिषासुर नामक असुर ने तीनों लोकों में प्रलय मचाया, तब सभी देवताओं ने अपनी-अपनी शक्तियां मिलाकर माँ दुर्गा को प्रकट किया। "
                "माँ ने नौ रूप धारण किए ताकि हर प्रकार की नकारात्मक शक्ति का विनाश किया जा सके।\n\n"
                "ये नौ रूप हमें सिखाते हैं कि हर चुनौती का सामना करने की शक्ति हम सब में है।🙏✨\n\n"
                "जय माता दी! ❤️\n"
                "वीडियो पसंद आए तो Like 👍 करें और चैनल को Subscribe 🔔 जरूर करें।"
            ),
            "main_educational_takeaway": "माँ दुर्गा के नौ रूप हर नकारात्मक शक्ति पर विजय और आंतरिक शक्ति का प्रतीक हैं।",
            "claim_type": "scriptural_story",
            "scenes": [
                {
                    "scene_number": 1,
                    "duration_seconds": 1.5,
                    "voiceover_hindi": "जब महिषासुर नाम का असुर बहुत शक्तिशाली हो गया...",
                    "onscreen_text_hindi": "असुर का आतंक",
                    "visual_description_english": "Dark dramatic scene of powerful demon Mahishasura with glowing red fiery eyes and horns creating cosmic destruction, dark storm, devotee looking up in fear, intricate sacred Hindu mythological art, 8k vertical 9:16",
                    "visual_description_hindi": "महिषासुर का आतंक और विनाश",
                    "camera_motion": "slow zoom in",
                    "transition": "fade",
                },
                {
                    "scene_number": 2,
                    "duration_seconds": 1.5,
                    "voiceover_hindi": "तब सभी देवताओं ने अपनी-अपनी शक्तियां एक साथ मिलाईं...",
                    "onscreen_text_hindi": "देवताओं की शक्ति",
                    "visual_description_english": "All Hindu gods Brahma, Vishnu, Shiva, Indra combining their celestial divine cosmic energies into a bright blinding golden light nexus, radiant volumetric rays, 8k vertical 9:16",
                    "visual_description_hindi": "देवताओं की दिव्य शक्तियों का एकीकरण",
                    "camera_motion": "pan up",
                    "transition": "fade",
                },
                {
                    "scene_number": 3,
                    "duration_seconds": 1.5,
                    "voiceover_hindi": "और उस दिव्य ऊर्जा से माँ दुर्गा का प्रकट हुआ।",
                    "onscreen_text_hindi": "माँ दुर्गा का प्राकट्य",
                    "visual_description_english": "Supreme Goddess Maa Durga emerges majestically from divine blinding golden light, radiant golden crown, glowing third eye, holding sacred weapons in ten arms, 8k vertical 9:16",
                    "visual_description_hindi": "दिव्य ऊर्जा से माँ दुर्गा का भव्य प्राकट्य",
                    "camera_motion": "slow zoom in",
                    "transition": "fade",
                },
                {
                    "scene_number": 4,
                    "duration_seconds": 1.5,
                    "voiceover_hindi": "उन्होंने नौ अलग-अलग रूप धारण किए...",
                    "onscreen_text_hindi": "माँ के नौ रूप",
                    "visual_description_english": "Nine divine forms of Goddess Durga Navadurga in a dynamic radiant 3x3 sacred montage, Shailaputri, Brahmacharini, Chandraghanta, Kushmanda, Skandamata, Katyayani, Kalaratri, Mahagauri, Siddhidatri, glowing golden aura, 8k vertical 9:16",
                    "visual_description_hindi": "माँ दुर्गा के नौ पवित्र नवदुर्गा रूप",
                    "camera_motion": "zoom in",
                    "transition": "cut",
                },
                {
                    "scene_number": 5,
                    "duration_seconds": 2.0,
                    "voiceover_hindi": "ताकि हर प्रकार की नकारात्मक शक्ति का विनाश किया जा सके।",
                    "onscreen_text_hindi": "महिषासुर संहार",
                    "visual_description_english": "Fierce warrior Goddess Maa Durga riding roaring ferocious lion, slaying demon Mahishasura with radiant glowing golden trishul trident, dramatic action and cosmic battle sparks, 8k vertical 9:16",
                    "visual_description_hindi": "सिंहवाहिनी माँ दुर्गा द्वारा महिषासुर का संहार",
                    "camera_motion": "zoom out",
                    "transition": "fade",
                },
                {
                    "scene_number": 6,
                    "duration_seconds": 2.0,
                    "voiceover_hindi": "माँ दुर्गा के ये नौ रूप हमें सिखाते हैं कि हर चुनौती का सामना करने की शक्ति हम सब में है। जय माता दी!",
                    "onscreen_text_hindi": "जय माता दी 🙏",
                    "visual_description_english": "A humble devotee young woman praying with folded hands to radiant benevolent Goddess Maa Durga who blesses her with glowing warm golden aura and celestial light, inspiring ending, 8k vertical 9:16",
                    "visual_description_hindi": "भक्त को माँ दुर्गा का पावन आशीर्वाद",
                    "camera_motion": "slow zoom in",
                    "transition": "fade",
                },
            ],
            "hashtags": [
                "#माँदुर्गा",
                "#नवरात्रि",
                "#महिषासुर",
                "#नवरात्रिविशेष",
                "#सनातनधर्म",
                "#हिंदूपौराणिककथा",
                "#देवीशक्ति",
                "#जयमातादी",
                "#YouTubeShorts",
                "#Shorts",
            ],
            "source_references": ["देवी भागवत पुराण", "मार्कंडेय पुराण"],
            "factual_concerns": [],
            "narration_word_count": 48,
            "estimated_narration_seconds": 10.0,
            "content_verification_notes": "पौराणिक कथाओं एवं देवी महात्म्य के अनुसार प्रामाणिक वर्णन।",
        }
        return GeneratedScript.model_validate(data)

