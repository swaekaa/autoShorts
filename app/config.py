"""
Application Configuration
==========================
All settings are loaded from environment variables (and an optional .env file).
No secrets are hard-coded. Every value has a safe default or raises a clear error
at startup when a required variable is missing.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Gemini / Google AI Studio ────────────────────────────────
    gemini_api_key: str = Field(..., description="Google AI Studio API key (Free tier: https://aistudio.google.com/app/apikey)")
    gemini_text_model: str = Field(
        default="gemini-flash-latest",
        description="Model identifier for text generation (Free tier: gemini-1.5-flash or gemini-2.5-flash).",
    )
    gemini_video_model: str = Field(
        default="veo-3.1-fast-generate-preview",
        description="Model identifier for video generation (used when visual_generator='veo').",
    )
    imagen_model: str = Field(
        default="imagen-3.0-generate-002",
        description="Official Google Imagen 3 model for high-resolution scene imagery.",
    )
    enable_pollinations_fallback: bool = Field(
        default=False,
        description="Whether to allow optional external pollinations fallback if Imagen 3 is unavailable. Disabled by default.",
    )
    visual_generator: Literal["free_motion", "veo"] = Field(
        default="free_motion",
        description="Visual engine: 'free_motion' (100% free dynamic vertical visuals with Ken Burns motion) or 'veo'.",
    )

    # ── Database ─────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./auto_shorts.db",
        description="Database URL. Defaults to local SQLite (zero-setup, no Docker needed). PostgreSQL also supported.",
    )

    # ── Google Cloud Storage ─────────────────────────────────────
    gcs_bucket_name: str = Field(default="", description="GCS bucket for asset storage (leave empty for local ./storage/)")
    gcs_project_id: str = Field(default="", description="Google Cloud project ID")
    google_application_credentials: str = Field(
        default="",
        description="Path to service-account JSON (optional when using edge TTS and local storage)",
    )

    # ── Text-to-Speech ───────────────────────────────────────────
    tts_provider: Literal["edge", "google"] = Field(
        default="edge",
        description="TTS provider: 'edge' (100% free studio Neural Hindi voices, no API key needed) or 'google'.",
    )
    tts_language_code: str = Field(default="hi-IN")
    tts_voice_name: str = Field(
        default="hi-IN-MadhurNeural",
        description="Voice: 'hi-IN-MadhurNeural' (male) or 'hi-IN-SwaraNeural' (female) for Edge; 'hi-IN-Neural2-B' for Google.",
    )
    tts_speaking_rate: float = Field(default=1.1, ge=0.5, le=2.0)

    # ── YouTube OAuth ────────────────────────────────────────────
    google_client_id: str = Field(default="", description="OAuth 2.0 Client ID")
    google_client_secret: str = Field(default="", description="OAuth 2.0 Client Secret")
    youtube_refresh_token: str = Field(default="", description="Persisted refresh token")
    youtube_channel_id: str = Field(
        default="",
        description="Target channel ID – verified before any upload",
    )

    # ── Publishing Controls ──────────────────────────────────────
    auto_publish: bool = Field(
        default=False,
        description="Must be explicitly enabled after manual testing",
    )
    video_privacy_status: Literal["public", "unlisted", "private"] = Field(
        default="public"
    )
    default_video_category_id: int = Field(default=27, description="27 = Education")

    # ── Budget and Rate Limits ───────────────────────────────────
    max_daily_videos: int = Field(default=5, ge=1, le=100)
    max_daily_spend_usd: float = Field(default=0.00, ge=0.0)
    max_queued_jobs: int = Field(default=3, ge=1, le=20)
    max_generation_retries: int = Field(default=4, ge=1, le=10)
    max_concurrent_generation_jobs: int = Field(default=1, ge=1, le=5)
    max_job_duration_minutes: int = Field(default=60, ge=5)

    # ── Video Spec ───────────────────────────────────────────────
    video_duration_seconds: int = Field(default=10)
    video_width: int = Field(default=1080)
    video_height: int = Field(default=1920)
    video_fps: int = Field(default=30)
    video_format: str = Field(default="mp4")
    video_codec: str = Field(default="libx264")
    audio_codec: str = Field(default="aac")

    # ── Worker / Scheduler ───────────────────────────────────────
    worker_poll_interval_seconds: int = Field(default=30, ge=5)
    video_gen_poll_interval_seconds: int = Field(default=20, ge=5)
    quota_cooldown_minutes: int = Field(default=65, ge=1)

    # ── API Server ───────────────────────────────────────────────
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    admin_api_key: str = Field(
        default="",
        description="Secret for admin endpoints",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # ── Emergency Stop ───────────────────────────────────────────
    emergency_stop: bool = Field(
        default=False,
        description="If True, all generation and publishing operations are halted immediately",
    )

    @field_validator("gemini_api_key")
    @classmethod
    def api_key_must_not_be_empty(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("GEMINI_API_KEY must be set (obtain free key from https://aistudio.google.com/app/apikey)")
        return v.strip()

    @field_validator("database_url")
    @classmethod
    def database_url_valid(cls, v: str) -> str:
        if not v or not v.strip():
            return "sqlite+aiosqlite:///./auto_shorts.db"
        v = v.strip()
        if not (v.startswith("postgresql") or v.startswith("sqlite")):
            raise ValueError("DATABASE_URL must be a SQLite or PostgreSQL URL")
        return v

    @model_validator(mode="after")
    def warn_on_missing_optional_secrets(self) -> "Settings":
        """Log warnings for features that will be unavailable without certain credentials."""
        import logging
        logger = logging.getLogger(__name__)
        if not self.google_client_id or not self.google_client_secret:
            logger.warning(
                "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not set. YouTube uploading disabled."
            )
        if not self.youtube_refresh_token:
            logger.warning(
                "YOUTUBE_REFRESH_TOKEN not set. YouTube uploading disabled. "
                "Run scripts/youtube_auth.py to obtain it."
            )
        if not self.gcs_bucket_name:
            logger.warning(
                "GCS_BUCKET_NAME not set. Assets will be stored locally in ./storage/."
            )
        if not self.admin_api_key:
            logger.warning(
                "ADMIN_API_KEY is empty – admin endpoints are unprotected! "
                "Set a strong random key in production."
            )
        return self

    @property
    def youtube_upload_enabled(self) -> bool:
        return bool(
            self.google_client_id
            and self.google_client_secret
            and self.youtube_refresh_token
        )

    @property
    def gcs_enabled(self) -> bool:
        return bool(self.gcs_bucket_name)

    @property
    def expected_video_frames(self) -> int:
        return self.video_duration_seconds * self.video_fps


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings singleton. Called at import time by dependencies."""
    return Settings()
