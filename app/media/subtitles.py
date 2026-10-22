"""
Subtitle Generator
==================
Converts script scene data into ASS subtitle format with Devanagari support.
ASS format provides better Unicode handling for Hindi text than SRT.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.schemas import GeneratedScript

logger = get_logger(__name__)


def generate_subtitles(
    script: GeneratedScript,
    output_path: str | Path,
    total_duration: float = 10.0,
) -> Path:
    """
    Generate an ASS subtitle file from the script's scene data.
    Distributes subtitle timing evenly across scenes.

    Returns the path to the written subtitle file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculate scene timings
    scenes = script.scenes
    if not scenes:
        # Fallback: show narration for full duration
        _write_minimal_ass(script.hindi_narration, output_path, total_duration)
        return output_path

    # Use scene duration_seconds if provided; normalize to sum == total_duration
    raw_durations = [s.duration_seconds for s in scenes]
    raw_total = sum(raw_durations)
    if raw_total > 0:
        scale = total_duration / raw_total
        durations = [d * scale for d in raw_durations]
    else:
        durations = [total_duration / len(scenes)] * len(scenes)

    # Build timing list
    timings: list[tuple[float, float, str]] = []
    current_time = 0.0
    for scene, duration in zip(scenes, durations):
        start = current_time
        end = current_time + duration
        
        # Prioritize scene-specific voiceover line if present, then onscreen text
        text = getattr(scene, "voiceover_hindi", "") or ""
        if not text:
            text = (scene.onscreen_text_hindi or "").strip()
        if not text:
            text = (scene.visual_description_hindi or "").strip()
        if not text and script.hindi_narration:
            words = script.hindi_narration.split()
            text = " ".join(words[:5]) if words else ""
            
        if text:
            timings.append((start, end, text))
        current_time = end

    _write_ass(timings, output_path)
    logger.info(
        "Subtitles generated",
        extra={"path": str(output_path), "subtitle_count": len(timings)},
    )
    return output_path


def _format_ass_time(seconds: float) -> str:
    """Format seconds as ASS timestamp: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _highlight_keywords(text: str) -> str:
    """
    Highlight key sacred and dramatic words in luminous gold/yellow {\\c&H00D7FF&}.
    """
    key_phrases = [
        "महिषासुर",
        "माँ दुर्गा का प्रकट",
        "माँ दुर्गा",
        "नौ अलग-अलग रूप",
        "नौ अलग-अलग",
        "दिव्य ऊर्जा",
        "नकारात्मक शक्ति",
        "विनाश",
        "जय माता दी",
    ]
    formatted = text
    for phrase in key_phrases:
        if phrase in formatted and "{\\c" not in formatted:
            highlight = f"{{\\c&H00D7FF&}}{{\\b1}}{phrase}{{\\b0}}{{\\c&HFFFFFF&}}"
            formatted = formatted.replace(phrase, highlight, 1)
            break
            
    # Highlight final invocation with a radiant red/gold badge
    if "जय माता दी" in formatted:
        formatted = formatted.replace(
            "जय माता दी",
            r"{\c&H0030FF&}{\b1}【 जय माता दी 🙏 】{\b0}{\c&HFFFFFF&}"
        )
    return formatted


def _write_ass(
    timings: list[tuple[float, float, str]],
    output_path: Path,
) -> None:
    """Write ASS subtitle file with Devanagari-compatible settings and gold highlights."""
    ass_header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Nirmala UI,46,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2.0,2,50,50,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [ass_header]
    for start, end, raw_text in timings:
        styled_text = _highlight_keywords(raw_text)
        line = (
            f"Dialogue: 0,"
            f"{_format_ass_time(start)},"
            f"{_format_ass_time(end)},"
            f"Default,,0,0,0,,{styled_text}"
        )
        lines.append(line)

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _write_minimal_ass(text: str, output_path: Path, duration: float) -> None:
    """Write a single subtitle spanning the full duration."""
    _write_ass([(0.0, duration, text[:80])], output_path)
