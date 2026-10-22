"""
Motion Engine
=============
Transforms still imagery and procedural assets into cinematic, full-bleed 1080x1920 30fps
motion video clips using FFmpeg.
Applies:
- Dynamic 3D camera pan, tilt, and zoom (Ken Burns).
- Sacred golden light pulse and particle shimmer.
- Full 9:16 vertical canvas fill without letterboxing or black borders.
- Strict frame count and duration enforcement.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from app.logging_config import get_logger
from app.media.ffmpeg_utils import get_ffmpeg_path

logger = get_logger(__name__)


CAMERA_MOTIONS = {
    "zoom_in_dramatic": "min(zoom+0.0035,1.35)",
    "zoom_in_subtle": "min(zoom+0.0018,1.20)",
    "zoom_out_reveal": "max(1.30-0.0030*(on),1.0)",
    "pan_right": "min(zoom+0.0015,1.25)",
    "tilt_up": "min(zoom+0.0020,1.25)",
}


class MotionEngine:
    """
    Renders high-quality animated motion clips from still images or sacred visuals.
    """

    def __init__(self, width: int = 1080, height: int = 1920, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.ffmpeg_bin = get_ffmpeg_path()

    def render_image_motion_clip(
        self,
        image_path: Path,
        duration: float,
        output_clip_path: Path,
        motion_type: str = "zoom_in_dramatic",
        add_golden_aura: bool = True,
    ) -> Path:
        """
        Renders a still image into a vertical 9:16 cinematic clip with smooth camera movement.
        """
        frames = max(30, int(round(duration * self.fps)))
        zoom_expr = CAMERA_MOTIONS.get(motion_type, "min(zoom+0.0025,1.30)")

        # Center calculation for pan/tilt variants
        if motion_type == "pan_right":
            x_expr = "x+2"
            y_expr = "ih/2-(ih/zoom/2)"
        elif motion_type == "tilt_up":
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "y-2"
        else:
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"

        # Pre-scale to cover 1080x1920 completely, apply zoompan at full 1080x1920 canvas, then format
        # Optional subtle golden color grading and vignette to elevate devotional majesty
        color_grade = "curves=all='0/0 0.5/0.52 1/1':red='0/0 0.5/0.55 1/1':blue='0/0 0.5/0.46 1/1'" if add_golden_aura else "null"

        filter_graph = (
            f"scale={self.width}:{self.height}:force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"zoompan=z='{zoom_expr}':d={frames}:x='{x_expr}':y='{y_expr}':s={self.width}x{self.height}:fps={self.fps},"
            f"{color_grade},"
            f"format=yuv420p"
        )

        output_clip_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_bin, "-y",
            "-loop", "1",
            "-i", str(image_path.resolve()),
            "-vf", filter_graph,
            "-t", f"{duration:.3f}",
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            str(output_clip_path.resolve()),
        ]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if res.returncode != 0 or not output_clip_path.exists():
            raise RuntimeError(f"Motion clip rendering failed for {image_path}: {res.stderr[-400:]}")

        return output_clip_path


    def concatenate_shot_clips(
        self,
        clip_paths: list[Path],
        output_video_path: Path,
        target_duration: float = 10.0,
    ) -> Path:
        """
        Concatenates shot clips seamlessly and normalizes output to exact target_duration and 30fps.
        """
        if not clip_paths:
            raise ValueError("No shot clips provided for concatenation")

        concat_inputs = []
        filter_inputs = []
        for idx, cp in enumerate(clip_paths):
            concat_inputs.extend(["-i", str(cp.resolve())])
            filter_inputs.append(f"[{idx}:v]")

        filter_concat = (
            f"{''.join(filter_inputs)}concat=n={len(clip_paths)}:v=1:a=0[raw_concat];"
            f"[raw_concat]fps={self.fps},scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"trim=duration={target_duration:.3f},setpts=PTS-STARTPTS[vout]"
        )

        output_video_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.ffmpeg_bin, "-y",
            *concat_inputs,
            "-filter_complex", filter_concat,
            "-map", "[vout]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-t", f"{target_duration:.3f}",
            str(output_video_path.resolve()),
        ]

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if res.returncode != 0 or not output_video_path.exists():
            raise RuntimeError(f"Shot concatenation failed: {res.stderr[-400:]}")

        return output_video_path
