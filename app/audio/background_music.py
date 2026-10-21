"""
Background Music
================
Generates or selects royalty-free background audio for Hindu Shorts.
Uses bundled ambient audio patterns synthesized via FFmpeg when no
external library is configured.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Literal

from app.logging_config import get_logger

logger = get_logger(__name__)

AudioMood = Literal["devotional", "peaceful", "energetic", "mystical"]


class BackgroundMusicGenerator:
    """
    Generates ambient background music using FFmpeg's built-in
    audio synthesis capabilities (no external API or license required).

    For higher quality, drop royalty-free audio files into
    ./storage/music/ and this class will use them preferentially.
    """

    MUSIC_DIR = Path("./storage/music")

    def __init__(self, settings=None):
        self._settings = settings
        self.MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    def get_or_generate(
        self,
        output_path: str | Path,
        duration_seconds: float = 10.0,
        mood: AudioMood = "devotional",
        volume: float = 0.15,
    ) -> Path:
        """
        Returns path to background music file.
        Prefers local files in MUSIC_DIR, falls back to synthesis.
        """
        output_path = Path(output_path)

        # Try to use pre-existing royalty-free audio
        existing = self._find_existing_music(mood)
        if existing:
            return self._trim_and_loop(existing, output_path, duration_seconds, volume)

        # Fall back to FFmpeg synthesis
        return self._synthesize_ambient(output_path, duration_seconds, volume, mood)

    def _find_existing_music(self, mood: AudioMood) -> Path | None:
        """Look for mood-tagged audio files in MUSIC_DIR."""
        for ext in ("mp3", "wav", "ogg", "flac"):
            for f in self.MUSIC_DIR.glob(f"*{mood}*.{ext}"):
                return f
            # Any audio file if mood-specific not found
            for f in self.MUSIC_DIR.glob(f"*.{ext}"):
                return f
        return None

    def _trim_and_loop(
        self,
        source: Path,
        output: Path,
        duration: float,
        volume: float,
    ) -> Path:
        """Trim or loop an audio file to exact duration."""
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",  # loop indefinitely
            "-i", str(source),
            "-t", str(duration),
            "-af", f"volume={volume},afade=t=out:st={duration - 0.5}:d=0.5",
            "-c:a", "aac",
            "-b:a", "128k",
            str(output),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.warning(
                "Music trim failed", extra={"stderr": result.stderr[:200]}
            )
        return output

    def _synthesize_ambient(
        self,
        output: Path,
        duration: float,
        volume: float,
        mood: AudioMood,
    ) -> Path:
        """
        Synthesize ambient drone music using FFmpeg's sine oscillators.
        Creates a devotional OM-like drone with harmonics.
        """
        # Fundamental frequency and harmonics vary by mood
        freq_map: dict[AudioMood, tuple[float, float, float]] = {
            "devotional": (136.1, 272.2, 408.3),   # OM frequency and overtones
            "peaceful": (174.0, 285.0, 396.0),
            "energetic": (220.0, 440.0, 660.0),
            "mystical": (111.0, 222.0, 333.0),
        }
        f1, f2, f3 = freq_map.get(mood, freq_map["devotional"])

        filter_complex = (
            f"sine=f={f1}:sample_rate=44100,"
            f"volume={volume * 0.5}[a];"
            f"sine=f={f2}:sample_rate=44100,"
            f"volume={volume * 0.3}[b];"
            f"sine=f={f3}:sample_rate=44100,"
            f"volume={volume * 0.2}[c];"
            "[a][b][c]amix=inputs=3,"
            f"afade=t=in:st=0:d=0.3,"
            f"afade=t=out:st={duration - 0.5}:d=0.5"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"sine=f={f1}:sample_rate=44100",
            "-f", "lavfi",
            "-i", f"sine=f={f2}:sample_rate=44100",
            "-f", "lavfi",
            "-i", f"sine=f={f3}:sample_rate=44100",
            "-filter_complex", filter_complex,
            "-t", str(duration),
            "-c:a", "aac",
            "-b:a", "128k",
            str(output),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.warning(
                "Ambient synthesis failed, generating silence",
                extra={"stderr": result.stderr[:200]},
            )
            # Last resort: generate silence
            self._generate_silence(output, duration)

        logger.info(
            "Background music generated",
            extra={"mood": mood, "duration": duration, "output": str(output)},
        )
        return output

    def _generate_silence(self, output: Path, duration: float) -> None:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r=44100:cl=stereo",
            "-t", str(duration),
            "-c:a", "aac",
            str(output),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
