"""
Scene Planner Module
====================
Plans a timed, multi-shot storyboard for high-retention 10-second YouTube Shorts.
Ensures a coherent visual narrative:
- 0.0 - 2.0s: Dramatic Hook (Close-up / Celestial reveal)
- 2.0 - 4.5s: Setting & Sacred Context
- 4.5 - 7.0s: Mythological Climax / Divine Energy
- 7.0 - 8.5s: Educational Revelation / Divine Attribute
- 8.5 - 10.0s: Powerful Devotional Benediction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from app.schemas import GeneratedScript, SceneDescription


@dataclass
class StoryboardShot:
    shot_index: int
    start_time: float
    end_time: float
    duration: float
    shot_type: str  # e.g., "close_up", "wide_temple", "action_climax", "celestial_aura"
    camera_motion: str  # e.g., "zoom_in_dramatic", "pan_right", "tilt_up", "zoom_out_reveal"
    visual_prompt: str
    onscreen_text: str = ""
    voiceover_text: str = ""


class ScenePlanner:
    """
    Constructs a timed storyboard of 4 to 5 distinct shots summing to exactly 10.0 seconds.
    """

    DEFAULT_TIMINGS = [
        (0.0, 2.0, "hook_close_up", "zoom_in_dramatic"),
        (2.0, 4.5, "setting_context", "tilt_up"),
        (4.5, 7.0, "mythological_climax", "pan_right"),
        (7.0, 8.5, "divine_revelation", "zoom_in_subtle"),
        (8.5, 10.0, "devotional_benediction", "zoom_out_reveal"),
    ]

    def create_storyboard(self, script: GeneratedScript) -> List[StoryboardShot]:
        """
        Create a balanced, strictly 10.0-second multi-shot storyboard from a script.
        """
        scenes = script.scenes or []
        shots: List[StoryboardShot] = []

        if len(scenes) >= 3:
            # Normalize provided scene durations so they sum to exactly 10.0s
            total_dur = sum(s.duration_seconds for s in scenes)
            scale = 10.0 / (total_dur if total_dur > 0 else 10.0)

            current_time = 0.0
            motion_styles = ["zoom_in_dramatic", "pan_right", "tilt_up", "zoom_in_subtle", "zoom_out_reveal"]

            for idx, scene in enumerate(scenes):
                # Calculate scaled duration
                if idx == len(scenes) - 1:
                    dur = round(10.0 - current_time, 2)
                else:
                    dur = max(1.5, round(scene.duration_seconds * scale, 2))

                end_time = min(10.0, round(current_time + dur, 2))
                if idx == len(scenes) - 1:
                    end_time = 10.0
                actual_dur = round(end_time - current_time, 2)

                motion = motion_styles[idx % len(motion_styles)]
                prompt = scene.visual_description_english or script.topic

                shots.append(
                    StoryboardShot(
                        shot_index=idx,
                        start_time=round(current_time, 2),
                        end_time=end_time,
                        duration=actual_dur,
                        shot_type=f"scene_{idx+1}",
                        camera_motion=motion,
                        visual_prompt=prompt,
                        onscreen_text=scene.onscreen_text_hindi or "",
                        voiceover_text=getattr(scene, "voiceover_hindi", "") or "",
                    )
                )
                current_time = end_time
        else:
            # Use standard 5-shot timed progression
            for idx, (start, end, shot_type, motion) in enumerate(self.DEFAULT_TIMINGS):
                prompt = f"{script.topic} - shot {idx+1}"
                shots.append(
                    StoryboardShot(
                        shot_index=idx,
                        start_time=start,
                        end_time=end,
                        duration=round(end - start, 2),
                        shot_type=shot_type,
                        camera_motion=motion,
                        visual_prompt=prompt,
                    )
                )

        return shots
