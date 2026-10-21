"""
SQLAlchemy ORM Models
=====================
All database tables for the Hindu Shorts Factory service.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────


class TopicCategory(str, enum.Enum):
    DEITY = "deity"
    MYTHOLOGY = "mythology"
    SCRIPTURE = "scripture"
    FESTIVAL = "festival"
    PHILOSOPHY = "philosophy"
    RITUAL = "ritual"
    TEMPLE = "temple"
    SYMBOLISM = "symbolism"
    TRADITION = "tradition"
    HISTORICAL = "historical"
    REGIONAL = "regional"
    OTHER = "other"


class TopicVerificationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    REJECTED = "rejected"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class JobStage(str, enum.Enum):
    TOPIC_SELECTED = "topic_selected"
    SCRIPT_GENERATED = "script_generated"
    TTS_GENERATED = "tts_generated"
    VIDEO_SUBMITTED = "video_submitted"
    VIDEO_POLLING = "video_polling"
    VIDEO_DOWNLOADED = "video_downloaded"
    AUDIO_MIXED = "audio_mixed"
    RENDERED = "rendered"
    VALIDATED = "validated"
    UPLOAD_PENDING = "upload_pending"
    UPLOADED = "uploaded"


class FailureCategory(str, enum.Enum):
    QUOTA_EXHAUSTED = "quota_exhausted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    GENERATION_ERROR = "generation_error"
    VALIDATION_ERROR = "validation_error"
    UPLOAD_ERROR = "upload_error"
    AUTH_ERROR = "auth_error"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class AssetType(str, enum.Enum):
    RAW_VIDEO = "raw_video"
    NARRATION_AUDIO = "narration_audio"
    BACKGROUND_MUSIC = "background_music"
    MIXED_AUDIO = "mixed_audio"
    SUBTITLED_VIDEO = "subtitled_video"
    FINAL_VIDEO = "final_video"
    THUMBNAIL = "thumbnail"
    SUBTITLE_FILE = "subtitle_file"


class PublicationStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"
    REMOVED = "removed"
    FAILED = "failed"


class QuotaEventType(str, enum.Enum):
    REQUEST = "request"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    SUCCESS = "success"
    ERROR = "error"
    RESET = "reset"
    COOLDOWN_STARTED = "cooldown_started"
    COOLDOWN_ENDED = "cooldown_ended"


class ServiceProvider(str, enum.Enum):
    GEMINI_TEXT = "gemini_text"
    GEMINI_VIDEO = "gemini_video"
    GOOGLE_TTS = "google_tts"
    YOUTUBE = "youtube"
    GCS = "gcs"


# ─────────────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────────────


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[TopicCategory] = mapped_column(
        Enum(TopicCategory, name="topic_category_enum"), nullable=False
    )
    language: Mapped[str] = mapped_column(String(10), default="hi", nullable=False)
    source_references: Mapped[list[Any]] = mapped_column(JSON, default=list)
    verification_status: Mapped[TopicVerificationStatus] = mapped_column(
        Enum(TopicVerificationStatus, name="topic_verification_status_enum"),
        default=TopicVerificationStatus.UNVERIFIED,
        nullable=False,
    )
    # SHA-256 of normalized topic_text for fast duplicate detection
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    jobs: Mapped[list["VideoJob"]] = relationship("VideoJob", back_populates="topic")

    __table_args__ = (Index("ix_topics_fingerprint", "fingerprint"),)


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("topics.id", ondelete="RESTRICT"), nullable=False
    )
    stage: Mapped[JobStage] = mapped_column(
        Enum(JobStage, name="job_stage_enum"),
        default=JobStage.TOPIC_SELECTED,
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status_enum"),
        default=JobStatus.PENDING,
        nullable=False,
    )
    # Full structured script data (JSON from Gemini)
    script_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Video generation operation ID (provider-specific)
    generation_operation_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_category: Mapped[FailureCategory | None] = mapped_column(
        Enum(FailureCategory, name="failure_category_enum"), nullable=True
    )
    error_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topic: Mapped[Topic] = relationship("Topic", back_populates="jobs")
    assets: Mapped[list["VideoAsset"]] = relationship("VideoAsset", back_populates="job")
    published_video: Mapped["PublishedVideo | None"] = relationship(
        "PublishedVideo", back_populates="job", uselist=False
    )

    __table_args__ = (
        Index("ix_video_jobs_status_stage", "status", "stage"),
        Index("ix_video_jobs_topic_id", "topic_id"),
    )


class VideoAsset(Base):
    __tablename__ = "video_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("video_jobs.id", ondelete="CASCADE"), nullable=False
    )
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type_enum"), nullable=False
    )
    # GCS key or local path
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # sha256 checksum for integrity
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    validation_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    job: Mapped[VideoJob] = relationship("VideoJob", back_populates="assets")

    __table_args__ = (Index("ix_video_assets_job_id", "job_id"),)


class PublishedVideo(Base):
    __tablename__ = "published_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("video_jobs.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status_enum"),
        default=PublicationStatus.PENDING,
        nullable=False,
    )
    # Persisted upload intent – set BEFORE initiating upload to prevent duplicates
    upload_intent_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    upload_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    upload_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    job: Mapped[VideoJob] = relationship("VideoJob", back_populates="published_video")

    __table_args__ = (UniqueConstraint("job_id", name="uq_published_videos_job_id"),)


class QuotaEvent(Base):
    __tablename__ = "quota_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[ServiceProvider] = mapped_column(
        Enum(ServiceProvider, name="service_provider_enum"), nullable=False
    )
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[QuotaEventType] = mapped_column(
        Enum(QuotaEventType, name="quota_event_type_enum"), nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Retry-After header value (seconds) if provided
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )

    __table_args__ = (Index("ix_quota_events_provider_ts", "provider", "event_timestamp"),)


class ServiceSettings(Base):
    __tablename__ = "service_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    emergency_stop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_daily_videos: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_daily_spend_usd: Mapped[float] = mapped_column(Float, default=2.00, nullable=False)
    max_queued_jobs: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    text_model: Mapped[str] = mapped_column(String(128), default="gemini-2.5-flash")
    video_model: Mapped[str] = mapped_column(String(128), default="veo-3.1-fast-generate-preview")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        # Only one settings row allowed
        Index("uq_service_settings_singleton", "id", unique=True),
    )
