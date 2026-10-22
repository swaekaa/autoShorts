"""
Prompt Builder Module
=====================
Builds rich, cinematic visual generation prompts for Hindu mythology and religious education.
Enforces:
- Accurate traditional iconography (ayudhas, vastra, mukut, mudras).
- 9:16 vertical framing without letterboxing.
- Dramatic cinematic lighting (volumetric god rays, glowing divine auras, cosmic lightning).
- High contrast, vibrant saffron, gold and crimson palettes.
- Prohibition of logos, watermarks, text, and modern artifacts.
"""

from __future__ import annotations

from typing import Dict, Any


DEITY_ICONOGRAPHY: Dict[str, Dict[str, str]] = {
    "ganesha": {
        "attributes": "Lord Ganesha, elephant head, gentle benevolent eyes, ornate golden crown (mukut), four arms holding parashu (axe) and pasha (noose), blessing abhaya mudra, bowl of sweet modakas",
        "clothing": "Vibrant pitambara silk dhoti, sacred thread (yajnopavita), jeweled gold ornaments and fresh marigold garland",
        "aura": "Brilliant radiant golden solar halo, warm divine aura of wisdom and auspiciousness",
        "colors": "Rich saffron (#FF9933), celestial gold (#FFD700), temple red (#B22222)",
    },
    "shiva": {
        "attributes": "Lord Shiva, tranquil meditative cosmic ascetic, crescent moon adorning matted locks (jatamukuta), river Ganga emerging, third eye on forehead, coiled blue serpent Vasuki around neck, holding sacred Trishula and Damru",
        "clothing": "Tiger skin wrap, rudraksha beads, sacred holy ash (vibhuti) marks",
        "aura": "Cosmic ethereal blue aura, mystical Himalayan mist, swirling celestial starlight and dancing divine flames",
        "colors": "Deep cosmic indigo, celestial cyan, radiant silver-gold, sacred ash grey",
    },
    "vishnu": {
        "attributes": "Lord Vishnu, serene four-armed supreme preserver, holding spinning glowing Sudarshana Chakra, pristine sacred Panchajanya shankha (conch), Gada (mace), and fragrant pink lotus (padma)",
        "clothing": "Brilliant pitambara yellow silk, Kaustubha gem glowing on chest, Vanamala flower garland, elaborate celestial crown",
        "aura": "Volumetric rays of blinding cosmic golden light, resting on great serpent Sheshanaga amidst milky ocean",
        "colors": "Deep royal blue, luminous celestial gold, emerald green accents",
    },
    "krishna": {
        "attributes": "Lord Krishna, divine dark complexion (Meghashyama), mesmerizing lotus-petal eyes, peacock feather (mayur pankh) in crown, playing enchanting golden flute (bansuri)",
        "clothing": "Silken yellow pitambara, delicate wild forest flower garland, jewel-encrusted ornaments",
        "aura": "Soft enchanted celestial moonlight mixed with golden sunset dust, surrounding cows and blooming Kadamba trees",
        "colors": "Peacock blue-green, butter yellow, divine sunset magenta",
    },
    "rama": {
        "attributes": "Lord Rama, embodiment of righteousness (Maryada Purushottama), noble heroic visage, carrying mighty Kodanda divine bow and quiver of golden arrows",
        "clothing": "Royal royal silk, warrior prince armor with intricate golden engravings, sacred crown",
        "aura": "Blinding sunbeam aura (Suryavansha glory), royal golden and saffron radiance",
        "colors": "Royal saffron, sunburst gold, deep ruby red, forest green",
    },
    "hanuman": {
        "attributes": "Lord Hanuman, colossal divine warrior monkey god, radiant golden-copper physique, holding massive golden Gada (mace), chest opened revealing Sita-Rama in heart",
        "clothing": "Saffron langot, sacred sacred thread, glowing pearl and gold ornaments",
        "aura": "Surging orange-golden divine fire aura, mountain-shaking celestial energy",
        "colors": "Fiery vermilion (Sindoor orange), burnished copper, golden yellow",
    },
    "durga": {
        "attributes": "Maa Durga, supreme Mahashakti, fierce yet motherly grace, riding a majestic roaring golden lion, ten arms wielding celestial weapons of all gods (chakra, sword, trishul, bow)",
        "clothing": "Magnificent red and gold bridal banarasi silk sari, ornate bridal gold jewelry and red bindi",
        "aura": "Thunderous cosmic lightning, radiating sun-like blinding halo, vanquishing cosmic darkness",
        "colors": "Deep crimson red, radiant sun gold, midnight black contrast",
    },
}


class PromptBuilder:
    """
    Builds shot-specific prompts enforcing vertical 9:16 cinematic Hindu devotional aesthetics.
    """

    @classmethod
    def identify_deity(cls, text: str) -> str | None:
        t = text.lower()
        if any(w in t for w in ("गणेश", "ganesh", "vinayaka", "विनायक", "vighnaharta")):
            return "ganesha"
        if any(w in t for w in ("शिव", "shiva", "shanker", "mahadev", "महादेव", "भोले", "नटराज", "nataraja")):
            return "shiva"
        if any(w in t for w in ("कृष्ण", "krishna", "kanha", "gopal", "गोपाल", "माधव")):
            return "krishna"
        if any(w in t for w in ("राम", "rama", "raghava", "raghuveer", "राघव")):
            return "rama"
        if any(w in t for w in ("विष्णु", "vishnu", "narayana", "नारायण", "avatar")):
            return "vishnu"
        if any(w in t for w in ("हनुमान", "hanuman", "bajrangbali", "बजरंगबली", "maruti")):
            return "hanuman"
        if any(w in t for w in ("दुर्गा", "durga", "kali", "काली", "shakti", "शक्ति", "chandi")):
            return "durga"
        return None

    @classmethod
    def build_shot_prompt(
        cls,
        topic: str,
        shot_type: str,
        scene_description: str,
        shot_index: int = 0,
    ) -> str:
        """
        Build an exhaustive, cinematic 9:16 vertical prompt for a single storyboard shot.
        """
        deity_key = cls.identify_deity(f"{topic} {scene_description}")
        deity_info = DEITY_ICONOGRAPHY.get(deity_key or "ganesha")

        # Shot-specific framing and perspective
        shot_framings = {
            "hook_close_up": "Dramatic extreme close-up shot focusing on the majestic divine face, ornate jeweled crown and glowing eyes.",
            "scene_1": "Dramatic low-angle cinematic hero shot, towering divine presence, volumetric god-rays piercing through clouds.",
            "setting_context": "Medium wide shot capturing the grand sacred ancient Hindu temple sanctum with towering carved stone pillars and oil lamps.",
            "scene_2": "Dynamic eye-level medium shot, showing sacred divine attributes, weapons, and intricate mudras in detail.",
            "mythological_climax": "Epic cinematic action shot with dramatic cosmic energy, swirling celestial lightning and vibrant glowing aura.",
            "scene_3": "High-contrast dynamic shot, divine power radiating outward, volumetric lighting and deep atmospheric shadows.",
            "divine_revelation": "Ethereal luminous shot, radiant golden halo filling the frame, floating glowing lotus petals and celestial light.",
            "scene_4": "Serene majestic portrait with soft warm rim lighting and celestial background.",
            "devotional_benediction": "Iconic full deity reveal in peaceful Abhaya blessing mudra, warm golden temple lights, incense smoke drifting peacefully.",
            "scene_5": "Grand devotional wide portrait, centered composition, sacred spiritual aura.",
        }

        framing = shot_framings.get(shot_type, shot_framings.get(f"scene_{shot_index+1}", "Cinematic vertical 9:16 portrait composition."))

        prompt_parts = [
            "Masterpiece vertical 9:16 cinematic Hindu mythological devotional art.",
            framing,
            f"Subject: {deity_info['attributes']}.",
            f"Attire & Adornments: {deity_info['clothing']}.",
            f"Atmosphere & Lighting: {deity_info['aura']}.",
            f"Color Palette: {deity_info['colors']}.",
            f"Scene Context: {scene_description.strip()}.",
            "Aesthetics: Photorealistic 8k octane render, hyper-detailed temple stone textures, volumetric mist, depth of field.",
            "Composition: Full-screen 9:16 aspect ratio, perfectly centered subject, NO letterboxing, NO black bars, NO text, NO watermarks, NO logos.",
        ]

        full_prompt = " ".join(prompt_parts)
        # Clean double spaces
        full_prompt = " ".join(full_prompt.split())
        return full_prompt
