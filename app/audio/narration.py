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
import wave
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.media.ffmpeg_utils import get_ffmpeg_path, get_ffprobe_path
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

                # Convert to AAC via FFmpeg if available, otherwise retain MP3
                final_path = mp3_path
                aac_path = output_path.with_suffix(".aac")
                ffmpeg_bin = get_ffmpeg_path()
                try:
                    cmd = [
                        ffmpeg_bin, "-y",
                        "-i", str(mp3_path),
                        "-c:a", "aac",
                        "-b:a", "192k",
                        str(aac_path),
                    ]
                    res = subprocess.run(cmd, capture_output=True, timeout=60)
                    if res.returncode == 0 and aac_path.exists():
                        final_path = aac_path
                except Exception as exc:
                    logger.debug("FFmpeg AAC conversion skipped/failed; using MP3 directly", extra={"error": str(exc)})

                duration = self._get_audio_duration(str(final_path), default_words_fallback=len(text.split()))
                logger.info(
                    "Edge TTS narration synthesized (Free Tier)",
                    extra={"voice": voice, "duration_seconds": duration, "path": str(final_path)},
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
                ffmpeg_bin = get_ffmpeg_path()
                cmd = [
                    ffmpeg_bin, "-y",
                    "-i", tmp_path,
                    "-c:a", "aac",
                    "-b:a", "192k",
                    str(aac_path),
                ]
                res = subprocess.run(cmd, capture_output=True, timeout=60)
                final_path = aac_path if (res.returncode == 0 and aac_path.exists()) else Path(tmp_path)
                duration = self._get_audio_duration(str(final_path), default_words_fallback=len(text.split()))
                return final_path, duration
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        # ── 3. Pure local fallback (silence/ambient audio) ────────────
        logger.warning("No TTS engine available; generating placeholder audio")
        fallback_path = output_path.with_suffix(".wav")
        try:
            # Generate 8 seconds of silent 16-bit 44.1kHz mono PCM via built-in wave module
            with wave.open(str(fallback_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(44100)
                wf.writeframes(b"\x00" * (44100 * 2 * 8))
            return fallback_path, 8.0
        except Exception as exc:
            logger.error("Failed to generate fallback wave audio", extra={"error": str(exc)})
            return fallback_path, 8.0

    def _get_audio_duration(self, path: str, default_words_fallback: int = 25) -> float:
        """Use ffprobe or fallback estimation to get audio duration in seconds."""
        ffprobe_bin = get_ffprobe_path()
        cmd = [
            ffprobe_bin, "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            path,
        ]
        try:
            import json
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                dur = float(data.get("format", {}).get("duration", 0.0))
                if dur > 0:
                    return dur
        except Exception:
            pass

        # Estimate duration based on word count (~2.5 words per sec for Hindi)
        est = round(max(4.0, min(15.0, default_words_fallback / 2.5)), 2)
        logger.info("Using estimated audio duration based on word count", extra={"duration_seconds": est})
        return est
