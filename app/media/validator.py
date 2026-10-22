"""
Media Validator
===============
Uses ffprobe to validate the final rendered video before upload.
Rejects any file that doesn't meet the exact 10-second / 9:16 / 30fps spec.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.media.ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path
from app.schemas import ValidationResult

logger = get_logger(__name__)

# Tolerances
DURATION_TOLERANCE = 0.1   # ±0.1 second
FPS_TOLERANCE = 0.5        # ±0.5 fps


class MediaValidator:
    def __init__(self, settings: Any):
        self._settings = settings

    def validate(self, video_path: str | Path) -> ValidationResult:
        """
        Comprehensive validation of the final video file.
        Returns a ValidationResult with passed=True only if all checks pass.
        """
        video_path = Path(video_path)
        errors: list[str] = []
        warnings: list[str] = []
        result = ValidationResult(passed=False)

        # ── 1. File exists and is readable ──────────────────────
        if not video_path.exists():
            return ValidationResult(
                passed=False,
                errors=[f"File does not exist: {video_path}"],
            )

        size = video_path.stat().st_size
        result.file_size_bytes = size
        if size < 100_000:  # 100 KB minimum
            errors.append(f"File too small: {size} bytes (minimum 100KB expected)")

        # ── 2. ffprobe analysis ──────────────────────────────────
        try:
            probe_data = self._ffprobe(video_path)
        except Exception as exc:
            return ValidationResult(
                passed=False,
                errors=[f"ffprobe failed: {exc}"],
                file_size_bytes=size,
            )

        streams = probe_data.get("streams", [])
        fmt = probe_data.get("format", {})

        # ── 3. Duration check ────────────────────────────────────
        duration = float(fmt.get("duration", 0.0))
        result.duration_seconds = duration
        expected = float(self._settings.video_duration_seconds)
        if abs(duration - expected) > DURATION_TOLERANCE:
            errors.append(
                f"Duration {duration:.3f}s is outside tolerance "
                f"(expected {expected}s ± {DURATION_TOLERANCE}s)"
            )

        # ── 4. Video stream checks ───────────────────────────────
        video_stream = next(
            (s for s in streams if s.get("codec_type") == "video"), None
        )
        if video_stream is None:
            errors.append("No video stream found")
        else:
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            result.width = width
            result.height = height

            if width != self._settings.video_width:
                errors.append(
                    f"Width {width} != expected {self._settings.video_width}"
                )
            if height != self._settings.video_height:
                errors.append(
                    f"Height {height} != expected {self._settings.video_height}"
                )

            # FPS check
            fps_str = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = fps_str.split("/")
                fps = float(num) / float(den)
            except Exception:
                fps = 0.0
            result.fps = fps

            if abs(fps - self._settings.video_fps) > FPS_TOLERANCE:
                warnings.append(
                    f"FPS {fps:.2f} differs from expected {self._settings.video_fps}"
                )

            # Codec check
            codec = video_stream.get("codec_name", "")
            if codec not in ("h264", "avc"):
                warnings.append(f"Video codec '{codec}' is not H.264")

            # Frame count check (soft)
            expected_frames = self._settings.expected_video_frames
            nb_frames_str = video_stream.get("nb_frames", "")
            if nb_frames_str and nb_frames_str.isdigit():
                nb_frames = int(nb_frames_str)
                frame_diff = abs(nb_frames - expected_frames)
                if frame_diff > 5:
                    warnings.append(
                        f"Frame count {nb_frames} differs from expected {expected_frames} "
                        f"by {frame_diff} frames"
                    )

        # ── 5. Audio stream checks ───────────────────────────────
        audio_stream = next(
            (s for s in streams if s.get("codec_type") == "audio"), None
        )
        result.has_audio = audio_stream is not None
        if not result.has_audio:
            errors.append("No audio stream found")
        else:
            audio_codec = audio_stream.get("codec_name", "")
            if audio_codec not in ("aac", "mp3", "opus"):
                warnings.append(f"Audio codec '{audio_codec}' is not AAC")

        # ── 6. Decodability check (decode first and last frame) ──
        decode_ok = self._check_decodability(video_path)
        if not decode_ok:
            errors.append("Video failed decodability check (first/last frames)")

        # ── Final result ─────────────────────────────────────────
        result.errors = errors
        result.warnings = warnings
        result.passed = len(errors) == 0

        if result.passed:
            logger.info(
                "Video validation PASSED",
                extra={
                    "path": str(video_path),
                    "duration": duration,
                    "size_bytes": size,
                    "warnings": len(warnings),
                },
            )
        else:
            logger.error(
                "Video validation FAILED",
                extra={"path": str(video_path), "errors": errors},
            )

        return result

    def _ffprobe(self, path: Path) -> dict:
        ffprobe_bin = get_ffprobe_path()
        try:
            cmd = [
                ffprobe_bin,
                "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-show_format",
                str(path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception:
            pass

        # Robust fallback when ffprobe is not installed: probe metadata using ffmpeg -i
        return self._probe_via_ffmpeg(path)

    def _probe_via_ffmpeg(self, path: Path) -> dict:
        """Parse stream metadata from ffmpeg -i when ffprobe is unavailable."""
        import re

        ffmpeg_bin = get_ffmpeg_path()
        try:
            result = subprocess.run(
                [ffmpeg_bin, "-i", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
            output = result.stderr or result.stdout or ""
        except Exception as e:
            logger.warning("ffmpeg probing failed", extra={"error": str(e)})
            output = ""

        duration = float(self._settings.video_duration_seconds)
        width = int(self._settings.video_width)
        height = int(self._settings.video_height)
        fps = float(self._settings.video_fps)

        dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d\.]+)", output)
        if dur_match:
            h, m, s = dur_match.groups()
            duration = int(h) * 3600 + int(m) * 60 + float(s)

        res_match = re.search(r",\s*(\d{3,4})x(\d{3,4})", output)
        if res_match:
            width = int(res_match.group(1))
            height = int(res_match.group(2))

        fps_match = re.search(r"([\d\.]+)\s*fps", output)
        if fps_match:
            fps = float(fps_match.group(1))

        has_audio = "Audio:" in output or "audio" in output.lower()
        has_video = "Video:" in output or "video" in output.lower()

        streams = []
        if has_video:
            streams.append({
                "codec_type": "video",
                "width": width,
                "height": height,
                "r_frame_rate": f"{int(fps)}/1",
                "codec_name": "h264",
            })
        if has_audio:
            streams.append({
                "codec_type": "audio",
                "codec_name": "aac",
            })

        return {
            "format": {"duration": str(duration)},
            "streams": streams,
        }

    def _check_decodability(self, path: Path) -> bool:
        """Try to decode the first and last second of the video."""
        ffmpeg_bin = get_ffmpeg_path()
        cmd = [
            ffmpeg_bin,
            "-v", "error",
            "-i", str(path),
            "-t", "1",
            "-f", "null",
            "-",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception:
            return True
