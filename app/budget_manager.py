"""
Budget Manager
==============
Tracks daily spending estimates and enforces the configured daily budget.
All cost estimates are clearly labelled as approximate when provider usage
data is unavailable.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QuotaEvent, VideoJob
from app.logging_config import get_logger

logger = get_logger(__name__)


# Approximate pricing as of late 2024/early 2025 – ALWAYS approximate.
# Verify current pricing at https://ai.google.dev/pricing and
# https://cloud.google.com/text-to-speech/pricing
APPROXIMATE_COSTS_USD = {
    # Gemini text generation – per 1M output tokens
    "gemini_text_per_1m_output_tokens": 0.30,   # Flash tier (verify current pricing)
    # Veo video generation – per second of output video
    "veo_per_second_video": 0.10,                # APPROXIMATE – pricing is preview/TBD
    # Google TTS Neural2 – per 1M characters
    "tts_neural2_per_1m_chars": 16.00,
    # YouTube Data API – no direct charge (quota units only)
    "youtube_per_upload": 0.0,
}


def estimate_script_generation_cost(output_tokens: int | None) -> float:
    """Estimate cost of one Gemini text call. Returns 0.0 if tokens unknown."""
    if output_tokens is None:
        logger.debug("Token count unavailable – cost labelled as approximate")
        return 0.001  # minimal approximate placeholder
    tokens_m = output_tokens / 1_000_000
    return tokens_m * APPROXIMATE_COSTS_USD["gemini_text_per_1m_output_tokens"]


def estimate_video_generation_cost(duration_seconds: float = 10.0) -> float:
    """Estimate cost of Veo generation. Clearly approximate."""
    return duration_seconds * APPROXIMATE_COSTS_USD["veo_per_second_video"]


def estimate_tts_cost(character_count: int) -> float:
    """Estimate cost of one TTS synthesis call."""
    chars_m = character_count / 1_000_000
    return chars_m * APPROXIMATE_COSTS_USD["tts_neural2_per_1m_chars"]


def _utc_today_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


class BudgetManager:
    def __init__(self, session: AsyncSession, settings: Any):
        self._db = session
        self._settings = settings

    async def get_daily_spend(self) -> float:
        """Sum all estimated costs recorded today."""
        today_start = _utc_today_start()
        result = await self._db.execute(
            select(func.coalesce(func.sum(QuotaEvent.estimated_cost_usd), 0.0)).where(
                QuotaEvent.event_timestamp >= today_start,
                QuotaEvent.estimated_cost_usd.is_not(None),
            )
        )
        return float(result.scalar_one() or 0.0)

    async def get_daily_video_count(self) -> int:
        """Count videos completed or uploaded today."""
        from app.models import JobStatus
        today_start = _utc_today_start()
        result = await self._db.execute(
            select(func.count(VideoJob.id)).where(
                VideoJob.completed_at >= today_start,
                VideoJob.status == JobStatus.COMPLETED,
            )
        )
        return int(result.scalar_one() or 0)

    async def can_generate(self) -> tuple[bool, str]:
        """
        Returns (True, "") if generation can proceed.
        Returns (False, reason) if a budget limit is reached.
        """
        daily_spend = await self.get_daily_spend()
        max_spend = self._settings.max_daily_spend_usd

        if daily_spend >= max_spend:
            return False, f"Daily budget exhausted: ${daily_spend:.4f} >= ${max_spend:.2f}"

        daily_videos = await self.get_daily_video_count()
        if daily_videos >= self._settings.max_daily_videos:
            return False, f"Daily video limit reached: {daily_videos}/{self._settings.max_daily_videos}"

        return True, ""

    async def get_remaining_budget(self) -> float:
        daily_spend = await self.get_daily_spend()
        return max(0.0, self._settings.max_daily_spend_usd - daily_spend)

    async def get_remaining_videos(self) -> int:
        daily_videos = await self.get_daily_video_count()
        return max(0, self._settings.max_daily_videos - daily_videos)
