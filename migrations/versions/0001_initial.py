"""Initial schema

Revision ID: 0001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("""
        CREATE TYPE topic_category_enum AS ENUM (
            'deity', 'mythology', 'scripture', 'festival', 'philosophy',
            'ritual', 'temple', 'symbolism', 'tradition', 'historical', 'regional', 'other'
        )
    """)
    op.execute("""
        CREATE TYPE topic_verification_status_enum AS ENUM (
            'unverified', 'verified', 'disputed', 'rejected'
        )
    """)
    op.execute("""
        CREATE TYPE job_status_enum AS ENUM (
            'pending', 'running', 'paused', 'completed', 'failed', 'abandoned'
        )
    """)
    op.execute("""
        CREATE TYPE job_stage_enum AS ENUM (
            'topic_selected', 'script_generated', 'tts_generated',
            'video_submitted', 'video_polling', 'video_downloaded',
            'audio_mixed', 'rendered', 'validated', 'upload_pending', 'uploaded'
        )
    """)
    op.execute("""
        CREATE TYPE failure_category_enum AS ENUM (
            'quota_exhausted', 'budget_exhausted', 'generation_error',
            'validation_error', 'upload_error', 'auth_error', 'timeout', 'unknown'
        )
    """)
    op.execute("""
        CREATE TYPE asset_type_enum AS ENUM (
            'raw_video', 'narration_audio', 'background_music', 'mixed_audio',
            'subtitled_video', 'final_video', 'thumbnail', 'subtitle_file'
        )
    """)
    op.execute("""
        CREATE TYPE publication_status_enum AS ENUM (
            'pending', 'uploaded', 'public', 'unlisted', 'private', 'removed', 'failed'
        )
    """)
    op.execute("""
        CREATE TYPE quota_event_type_enum AS ENUM (
            'request', 'rate_limited', 'quota_exceeded', 'success', 'error',
            'reset', 'cooldown_started', 'cooldown_ended'
        )
    """)
    op.execute("""
        CREATE TYPE service_provider_enum AS ENUM (
            'gemini_text', 'gemini_video', 'google_tts', 'youtube', 'gcs'
        )
    """)

    # topics table
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic_text", sa.Text(), nullable=False),
        sa.Column("category", postgresql.ENUM(name="topic_category_enum", create_type=False), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="hi"),
        sa.Column("source_references", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("verification_status", postgresql.ENUM(name="topic_verification_status_enum", create_type=False), nullable=False, server_default="unverified"),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint"),
    )
    op.create_index("ix_topics_fingerprint", "topics", ["fingerprint"])

    # video_jobs table
    op.create_table(
        "video_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("stage", postgresql.ENUM(name="job_stage_enum", create_type=False), nullable=False, server_default="topic_selected"),
        sa.Column("status", postgresql.ENUM(name="job_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("script_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("generation_operation_id", sa.String(length=512), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_category", postgresql.ENUM(name="failure_category_enum", create_type=False), nullable=True),
        sa.Column("error_details", sa.Text(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_jobs_status_stage", "video_jobs", ["status", "stage"])
    op.create_index("ix_video_jobs_topic_id", "video_jobs", ["topic_id"])

    # video_assets table
    op.create_table(
        "video_assets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("asset_type", postgresql.ENUM(name="asset_type_enum", create_type=False), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("validation_details", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["video_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_video_assets_job_id", "video_assets", ["job_id"])

    # published_videos table
    op.create_table(
        "published_videos",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=64), nullable=True),
        sa.Column("video_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("publication_status", postgresql.ENUM(name="publication_status_enum", create_type=False), nullable=False, server_default="pending"),
        sa.Column("upload_intent_token", sa.String(length=64), nullable=True),
        sa.Column("upload_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("upload_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["video_jobs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="uq_published_videos_job_id"),
        sa.UniqueConstraint("youtube_video_id"),
        sa.UniqueConstraint("upload_intent_token"),
    )

    # quota_events table
    op.create_table(
        "quota_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider", postgresql.ENUM(name="service_provider_enum", create_type=False), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", postgresql.ENUM(name="quota_event_type_enum", create_type=False), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("observed_usage", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quota_events_provider_ts", "quota_events", ["provider", "event_timestamp"])

    # service_settings table
    op.create_table(
        "service_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("auto_publish", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("emergency_stop", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("max_daily_videos", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("max_daily_spend_usd", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("max_queued_jobs", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("text_model", sa.String(length=128), nullable=False, server_default="gemini-2.5-flash"),
        sa.Column("video_model", sa.String(length=128), nullable=False, server_default="veo-3.1-fast-generate-preview"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Insert default settings row
    op.execute("""
        INSERT INTO service_settings (id, enabled, auto_publish, emergency_stop)
        VALUES (1, true, false, false)
    """)


def downgrade() -> None:
    op.drop_table("service_settings")
    op.drop_table("quota_events")
    op.drop_table("published_videos")
    op.drop_table("video_assets")
    op.drop_table("video_jobs")
    op.drop_table("topics")

    for enum_name in [
        "service_provider_enum", "quota_event_type_enum", "publication_status_enum",
        "asset_type_enum", "failure_category_enum", "job_stage_enum", "job_status_enum",
        "topic_verification_status_enum", "topic_category_enum"
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
