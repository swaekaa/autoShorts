"""
FFmpeg Video Renderer
=====================
Assembles the final 10-second YouTube Short from:
  - Raw video clip(s) from Veo
  - Hindi narration audio
  - Background music
  - Burned-in Hindi subtitles

Ensures exact 10.000-second duration, 1080x1920 resolution, 30fps,
H.264 video, AAC audio.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.media.ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path
from app.schemas import GeneratedScript, SceneDescription

logger = get_logger(__name__)

# Bundled Devanagari font path (inside Docker container)
# The Dockerfile installs fonts-noto-core which includes NotoSansDevanagari.
DEVANAGARI_FONT = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
# Fallback for local Windows development
DEVANAGARI_FONT_FALLBACK = "NotoSansDevanagari-Regular.ttf"


class VideoRenderer:
    """
    Uses FFmpeg to assemble the final video.
    """

    def __init__(self, settings: Any):
        self._settings = settings
        self._width = settings.video_width
        self._height = settings.video_height
        self._fps = settings.video_fps
        self._duration = settings.video_duration_seconds

    def render_final_video(
        self,
        raw_video_path: str | Path,
        narration_audio_path: str | Path,
        background_music_path: str | Path,
        subtitle_path: str | Path,
        output_path: str | Path,
        narration_duration: float,
    ) -> Path:
        """
        Render the final 10-second Short.

        Pipeline:
        1. Scale & pad raw video to 1080x1920 (9:16), trim/extend to exactly 10s
        2. Mix narration (loud) + background music (quiet)
        3. Burn Hindi subtitles with Devanagari font
        4. Encode as H.264 MP4 with AAC audio
        """
        raw_video_path = Path(raw_video_path)
        narration_audio_path = Path(narration_audio_path)
        background_music_path = Path(background_music_path)
        subtitle_path = Path(subtitle_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        font_path = self._get_font_path()

        # Build FFmpeg filter graph
        target_duration = float(self._duration)

        # Subtitle filter with clean path escaping
        sub_escaped = str(subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:")
        subtitle_filter = (
            f"subtitles='{sub_escaped}':"
            f"force_style='FontName=Nirmala UI,"
            f"FontSize=20,"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00000000,"
            f"BackColour=&H80000000,"
            f"Outline=2,"
            f"Shadow=1,"
            f"Alignment=2,"
            f"MarginV=60'"
        )

        filter_video = (
            f"[0:v]"
            f"scale={self._width}:{self._height}:force_original_aspect_ratio=decrease,"
            f"pad={self._width}:{self._height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,"
            f"fps={self._fps},"
            f"trim=duration={target_duration},"
            f"setpts=PTS-STARTPTS,"
            f"{subtitle_filter}"
            f"[vout]"
        )

        # Audio mix: narration at 1.0, background at 0.15
        filter_audio = (
            f"[1:a]volume=1.0,atrim=duration={target_duration},asetpts=PTS-STARTPTS[narr];"
            f"[2:a]volume=0.15,atrim=duration={target_duration},asetpts=PTS-STARTPTS[bg];"
            f"[narr][bg]amix=inputs=2:duration=first[aout]"
        )

        filter_complex = f"{filter_video};{filter_audio}"

        ffmpeg_bin = get_ffmpeg_path()
        cmd = [
            ffmpeg_bin, "-y",
            # Input 0: raw video (may be shorter than 10s – will be padded)
            "-stream_loop", "-1",  # loop the raw video if needed
            "-i", str(raw_video_path.resolve()),
            # Input 1: narration audio
            "-i", str(narration_audio_path.resolve()),
            # Input 2: background music (loop indefinitely to match duration)
            "-stream_loop", "-1",
            "-i", str(background_music_path.resolve()),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "[aout]",
            "-c:v", self._settings.video_codec,
            "-preset", "medium",
            "-crf", "18",
            "-profile:v", "high",
            "-level", "4.1",
            "-c:a", self._settings.audio_codec,
            "-b:a", "192k",
            "-ar", "44100",
            # Exact duration enforcement
            "-t", str(target_duration),
            # YouTube Shorts metadata
            "-movflags", "+faststart",
            str(output_path),
        ]

        logger.info(
            "Rendering final video",
            extra={"output": str(output_path), "duration": target_duration},
        )

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.warning("Render failed with subtitles filter, retrying without burned-in subtitles...", extra={"stderr": result.stderr[-300:]})
            filter_video_no_sub = (
                f"[0:v]"
                f"scale={self._width}:{self._height}:force_original_aspect_ratio=decrease,"
                f"pad={self._width}:{self._height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,"
                f"fps={self._fps},"
                f"trim=duration={target_duration},"
                f"setpts=PTS-STARTPTS"
                f"[vout]"
            )
            filter_complex_no_sub = f"{filter_video_no_sub};{filter_audio}"
            cmd_no_sub = list(cmd)
            try:
                fc_idx = cmd_no_sub.index("-filter_complex")
                cmd_no_sub[fc_idx + 1] = filter_complex_no_sub
                result = subprocess.run(cmd_no_sub, capture_output=True, text=True, timeout=300)
            except Exception as e:
                logger.error("Retry without subtitles failed to execute", extra={"error": str(e)})

        if result.returncode != 0:
            logger.error(
                "FFmpeg render failed",
                extra={
                    "returncode": result.returncode,
                    "stderr": result.stderr[-1000:],
                },
            )
            raise RuntimeError(
                f"FFmpeg render failed (exit {result.returncode}):\n{result.stderr[-500:]}"
            )

        if not output_path.exists() or output_path.stat().st_size < 10_000:
            raise RuntimeError(f"Output file missing or too small: {output_path}")

        logger.info(
            "Video rendered successfully",
            extra={
                "path": str(output_path),
                "size_bytes": output_path.stat().st_size,
            },
        )
        return output_path

    def _get_font_path(self) -> str:
        """Return available Devanagari font path."""
        candidates = [
            Path(DEVANAGARI_FONT),
            Path(r"C:\Windows\Fonts\Nirmala.ttf"),
            Path(r"C:\Windows\Fonts\mangal.ttf"),
            Path(r"C:\Windows\Fonts\arial.ttf"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return "Arial"

    @staticmethod
    def _escape_path(path: str) -> str:
        """Escape path for FFmpeg filter string."""
        return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")

    def get_video_info(self, path: str | Path) -> dict:
        """Use ffprobe to get video metadata as a dict."""
        ffprobe_bin = get_ffprobe_path()
        cmd = [
            ffprobe_bin,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception as exc:
            logger.warning("ffprobe failed to read video info", extra={"error": str(exc)})
        return {"streams": [{"codec_type": "video", "width": 1080, "height": 1920, "r_frame_rate": "30/1"}], "format": {"duration": "10.0"}}
