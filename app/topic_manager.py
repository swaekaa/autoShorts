"""
Topic Manager
=============
Manages Hindu religion/mythology topic discovery, deduplication,
and selection for video generation.
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Topic, TopicCategory, TopicVerificationStatus
from app.logging_config import get_logger

logger = get_logger(__name__)


# Curated topic seed list – expanded dynamically by Gemini
SEED_TOPICS: list[dict[str, Any]] = [
    # Deities
    {"text": "भगवान गणेश का विघ्नहर्ता स्वरूप", "category": TopicCategory.DEITY},
    {"text": "भगवान शिव का नटराज रूप और ब्रह्मांडीय नृत्य", "category": TopicCategory.DEITY},
    {"text": "माँ दुर्गा ने नौ रूप क्यों धारण किए?", "category": TopicCategory.MYTHOLOGY},
    {"text": "माँ दुर्गा और महिषासुर का युद्ध", "category": TopicCategory.MYTHOLOGY},
    {"text": "भगवान विष्णु के दशावतार", "category": TopicCategory.DEITY},
    {"text": "भगवान कृष्ण और सुदामा की मित्रता", "category": TopicCategory.MYTHOLOGY},
    {"text": "भगवान राम का वनवास और सीता की खोज", "category": TopicCategory.MYTHOLOGY},
    {"text": "हनुमान जी की संजीवनी बूटी लाने की कथा", "category": TopicCategory.MYTHOLOGY},
    # Philosophy
    {"text": "भगवद्गीता में कर्मयोग का सिद्धांत", "category": TopicCategory.PHILOSOPHY},
    {"text": "धर्म, अर्थ, काम, मोक्ष – चतुर्वर्ग", "category": TopicCategory.PHILOSOPHY},
    {"text": "आत्मा की अमरता और पुनर्जन्म का सिद्धांत", "category": TopicCategory.PHILOSOPHY},
    # Scriptures
    {"text": "ऋग्वेद की प्रथम ऋचा और उसका अर्थ", "category": TopicCategory.SCRIPTURE},
    {"text": "उपनिषदों में ब्रह्म और आत्मा का संबंध", "category": TopicCategory.SCRIPTURE},
    # Festivals
    {"text": "दिवाली – प्रकाश का पर्व और उसका महत्व", "category": TopicCategory.FESTIVAL},
    {"text": "होली का त्योहार और प्रह्लाद की कथा", "category": TopicCategory.FESTIVAL},
    {"text": "नवरात्रि के नौ रूपों का महत्व", "category": TopicCategory.FESTIVAL},
    # Symbolism
    {"text": "ॐ का अर्थ और आध्यात्मिक महत्व", "category": TopicCategory.SYMBOLISM},
    {"text": "त्रिशूल का प्रतीकात्मक अर्थ", "category": TopicCategory.SYMBOLISM},
    {"text": "स्वस्तिक का पवित्र अर्थ और इतिहास", "category": TopicCategory.SYMBOLISM},
    # Temples
    {"text": "काशी विश्वनाथ मंदिर का इतिहास", "category": TopicCategory.TEMPLE},
    {"text": "तिरुपति बालाजी मंदिर की परंपराएं", "category": TopicCategory.TEMPLE},
    # Traditions
    {"text": "संध्यावंदन की परंपरा और उसका वैज्ञानिक आधार", "category": TopicCategory.TRADITION},
    {"text": "पंचामृत अभिषेक की विधि और महत्व", "category": TopicCategory.RITUAL},
]


def _compute_fingerprint(text: str) -> str:
    """SHA-256 of NFKC-normalized lowercase text for deduplication."""
    normalized = unicodedata.normalize("NFKC", text.lower().strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class TopicManager:
    def __init__(self, session: AsyncSession):
        self._db = session

    async def get_or_create_topic(
        self,
        topic_text: str,
        category: TopicCategory,
        source_references: list[str] | None = None,
    ) -> tuple[Topic, bool]:
        """
        Returns (topic, created).
        If a topic with the same fingerprint exists, returns the existing one.
        """
        fingerprint = _compute_fingerprint(topic_text)

        result = await self._db.execute(
            select(Topic).where(Topic.fingerprint == fingerprint)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing, False

        topic = Topic(
            topic_text=topic_text,
            category=category,
            language="hi",
            source_references=source_references or [],
            fingerprint=fingerprint,
            verification_status=TopicVerificationStatus.UNVERIFIED,
        )
        self._db.add(topic)
        await self._db.flush()  # get ID without committing
        logger.info("New topic created", extra={"topic_id": topic.id, "category": category.value})
        return topic, True

    async def get_used_fingerprints(self) -> set[str]:
        """Return fingerprints of topics that have associated completed/uploaded jobs."""
        from app.models import VideoJob, JobStatus
        result = await self._db.execute(
            select(Topic.fingerprint)
            .join(VideoJob, VideoJob.topic_id == Topic.id)
            .where(VideoJob.status.in_([JobStatus.COMPLETED]))
        )
        return {row[0] for row in result.all()}

    async def seed_topics(self) -> int:
        """Insert seed topics that don't already exist. Returns count inserted."""
        created = 0
        for seed in SEED_TOPICS:
            _, is_new = await self.get_or_create_topic(
                topic_text=seed["text"],
                category=seed["category"],
            )
            if is_new:
                created += 1
        await self._db.commit()
        logger.info("Seed topics processed", extra={"count_created": created})
        return created

    async def get_unused_topics(self, limit: int = 10) -> list[Topic]:
        """Return topics that haven't been successfully completed yet."""
        from app.models import VideoJob, JobStatus
        # Topics with no completed jobs
        subq = (
            select(VideoJob.topic_id)
            .where(VideoJob.status == JobStatus.COMPLETED)
        )
        result = await self._db.execute(
            select(Topic)
            .where(Topic.id.not_in(subq))
            .order_by(Topic.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_all_topic_texts(self) -> list[str]:
        """Get all existing topic texts for Gemini context (avoid duplicates)."""
        result = await self._db.execute(select(Topic.topic_text))
        return [row[0] for row in result.all()]
