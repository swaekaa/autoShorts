"""
Pydantic Schemas (API request/response models)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import (
    AssetType,
    FailureCategory,
    JobStage,
    JobStatus,
    PublicationStatus,
    QuotaEventType,
    ServiceProvider,
    TopicCategory,
    TopicVerificationStatus,
)


# ── Topic ────────────────────────────────────────────────────────

class TopicRead(BaseModel):
    id: int
    topic_text: str
    category: TopicCategory
    language: str
    source_references: list[Any]
    verification_status: TopicVerificationStatus
    fingerprint: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Video Job ────────────────────────────────────────────────────

class VideoJobRead(BaseModel):
    id: int
    topic_id: int
    stage: JobStage
    status: JobStatus
    retry_count: int
    failure_category: FailureCategory | None
    error_details: str | None
    estimated_cost_usd: float
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class VideoJobDetail(VideoJobRead):
    script_data: dict[str, Any] | None
    generation_operation_id: str | None
    next_retry_at: datetime | None


# ── Video Asset ──────────────────────────────────────────────────

class VideoAssetRead(BaseModel):
    id: int
    job_id: int
    asset_type: AssetType
    storage_key: str
    mime_type: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    file_size_bytes: int | None
    checksum: str | None
    validation_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Published Video ──────────────────────────────────────────────

class PublishedVideoRead(BaseModel):
    id: int
    job_id: int
    youtube_video_id: str | None
    video_url: str | None
    title: str | None
    publication_status: PublicationStatus
    upload_completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Quota Event ──────────────────────────────────────────────────

class QuotaEventRead(BaseModel):
    id: int
    provider: ServiceProvider
    model_id: str | None
    event_type: QuotaEventType
    error_code: str | None
    retry_after_seconds: int | None
    estimated_cost_usd: float | None
    event_timestamp: datetime

    model_config = {"from_attributes": True}


# ── Service Settings ─────────────────────────────────────────────

class ServiceSettingsRead(BaseModel):
    enabled: bool
    auto_publish: bool
    emergency_stop: bool
    max_daily_videos: int
    max_daily_spend_usd: float
    max_queued_jobs: int
    text_model: str
    video_model: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class ServiceSettingsUpdate(BaseModel):
    enabled: bool | None = None
    auto_publish: bool | None = None
    emergency_stop: bool | None = None
    max_daily_videos: int | None = Field(default=None, ge=1, le=100)
    max_daily_spend_usd: float | None = Field(default=None, ge=0.0)
    max_queued_jobs: int | None = Field(default=None, ge=1, le=20)


# ── Health Check ─────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    worker_running: bool
    emergency_stop: bool
    daily_videos_today: int
    estimated_daily_spend_usd: float


# ── Worker Status ─────────────────────────────────────────────────

class WorkerStatusResponse(BaseModel):
    state: str
    active_jobs: int
    queued_jobs: int
    completed_today: int
    failed_today: int
    quota_states: dict[str, str]
    next_scheduled: datetime | None


# ── Script Generation (internal Pydantic schemas used with Gemini) ──

class SceneDescription(BaseModel):
    scene_number: int = Field(..., ge=1, le=10)
    duration_seconds: float = Field(..., ge=0.5, le=5.0)
    visual_description_hindi: str
    visual_description_english: str
    onscreen_text_hindi: str
    camera_motion: str = Field(default="static")
    transition: str = Field(default="cut")


class GeneratedScript(BaseModel):
    """Structured output from Gemini script generation."""
    topic: str
    topic_category: TopicCategory
    main_educational_takeaway: str
    claim_type: str = Field(
        ...,
        description="One of: scriptural_account | traditional_interpretation | historical_claim | modern_scholarly_interpretation",
    )
    source_references: list[str] = Field(default_factory=list)
    hindi_narration: str = Field(
        ...,
        description="Full Hindi narration text. Target 18-25 words for ~10 second speech.",
    )
    narration_word_count: int
    scenes: list[SceneDescription] = Field(..., min_length=1, max_length=8)
    video_title_hindi: str
    video_description_hindi: str
    hashtags: list[str] = Field(..., max_length=30)
    content_verification_notes: str
    factual_concerns: list[str] = Field(default_factory=list)
    estimated_narration_seconds: float


class ValidationResult(BaseModel):
    passed: bool
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    has_audio: bool = False
    file_size_bytes: int | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
