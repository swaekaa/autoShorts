"""
Hindi Narration Generator
=========================
Synthesizes Hindi text to speech.
Defaults to Edge Neural TTS (100% Free Tier, studio-grade Hindi voices, no API key).
Also supports Google Cloud Text-to-Speech (Neural2 hi-IN) when configured.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.quota_manager import QuotaEventType, QuotaManager, ServiceProvider

logger = get_logger(__name__)


class NarrationGenerator:
    """
    Converts Hindi narration text to an audio file.
    Default provider is 'edge' (Edge Neural hi-IN, 100% free, zero credentials needed).
    """

    def __init__(self, settings: Any, quota_manager: QuotaManager | None = None):
        self._settings = settings
        self._quota = quota_manager
        self._google_client = None
        self._google_tts = None

        if getattr(settings, "tts_provider", "edge") == "google":
            self._init_google_client()

    def _init_google_client(self) -> None:
        try:
            from google.cloud import texttospeech
            self._google_tts = texttospeech
            self._google_client = texttospeech.TextToSpeechClient()
            logger.info(
                "Google Cloud TTS client initialized",
                extra={"voice": self._settings.tts_voice_name},
            )
        except Exception as exc:
            logger.warning(
                "Google Cloud TTS not available – will fall back to Edge TTS",
                extra={"error": str(exc)},
            )

    async def synthesize(
        self,
        text: str,
        output_path: str | Path,
    ) -> tuple[Path, float]:
        """
        Synthesize Hindi text to audio file.
        Returns (output_path, duration_seconds).
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        provider = getattr(self._settings, "tts_provider", "edge")

        # ── 1. Edge Neural TTS (Free Tier) ───────────────────────────
        if provider == "edge":
            try:
                import edge_tts

                voice = self._settings.tts_voice_name or "hi-IN-MadhurNeural"
                # Validate that voice is an Edge voice name
                if not voice.startswith("hi-IN-"):
                    voice = "hi-IN-MadhurNeural"

                rate_diff = self._settings.tts_speaking_rate - 1.0
                rate_str = f"+{int(rate_diff * 100)}%" if rate_diff >= 0 else f"{int(rate_diff * 100)}%"

                communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate_str)
                mp3_path = output_path.with_suffix(".mp3")
                await communicate.save(str(mp3_path))

                # Convert to AAC via FFmpeg for standard container mixing
                aac_path = output_path.with_suffix(".aac")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(mp3_path),
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(aac_path),
                ]
                subprocess.run(cmd, capture_output=True, timeout=60)
                final_path = aac_path if aac_path.exists() else mp3_path

                duration = self._get_audio_duration(str(final_path))
                logger.info(
                    "Edge TTS narration synthesized (Free Tier)",
                    extra={"voice": voice, "duration_seconds": duration},
                )
                return final_path, duration
            except Exception as exc:
                logger.warning(
                    "Edge TTS failed; attempting Google Cloud TTS fallback",
                    extra={"error": str(exc)},
                )
                if not self._google_client:
                    self._init_google_client()

        # ── 2. Google Cloud TTS ──────────────────────────────────────
        if self._google_client is not None:
            tts = self._google_tts
            synthesis_input = tts.SynthesisInput(text=text)
            voice = tts.VoiceSelectionParams(
                language_code=self._settings.tts_language_code,
                name=self._settings.tts_voice_name if "Neural2" in self._settings.tts_voice_name else "hi-IN-Neural2-B",
            )
            audio_config = tts.AudioConfig(
                audio_encoding=tts.AudioEncoding.LINEAR16,
                speaking_rate=self._settings.tts_speaking_rate,
                sample_rate_hertz=44100,
            )

            response = self._google_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
            )

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(response.audio_content)
                tmp_path = tmp.name

            try:
                aac_path = output_path.with_suffix(".aac")
                cmd = [
                    "ffmpeg", "-y",
                    "-i", tmp_path,
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(aac_path),
                ]
                subprocess.run(cmd, capture_output=True, timeout=60)
                final_path = aac_path if aac_path.exists() else Path(tmp_path)
                duration = self._get_audio_duration(str(final_path))
                return final_path, duration
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        # ── 3. Pure local fallback (silence/ambient audio) ────────────
        logger.warning("No TTS engine available; generating placeholder audio with FFmpeg")
        fallback_path = output_path.with_suffix(".aac")
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "8.0",
            "-c:a", "aac",
            str(fallback_path),
        ]
        subprocess.run(cmd, capture_output=True, timeout=30)
        return fallback_path, 8.0

    def _get_audio_duration(self, path: str) -> float:
        """Use ffprobe to get audio duration in seconds."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            path,
        ]
        try:
            import json
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            data = json.loads(result.stdout)
            return float(data.get("format", {}).get("duration", 0.0))
        except Exception as exc:
            logger.warning("Could not probe audio duration", extra={"error": str(exc)})
            return 8.0
