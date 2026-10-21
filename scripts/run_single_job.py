"""
CLI Tool: Run Single Video Job
==============================
Manually triggers script generation, rendering, and optional publishing
for a specific topic or an autonomous next topic.

Usage:
    # Run full dry-run (generate script & validate without uploading)
    python scripts/run_single_job.py --dry-run

    # Generate for a specific topic
    python scripts/run_single_job.py --topic "शिव तांडव स्तोत्र का रहस्य" --category scripture

    # Force publish even if AUTO_PUBLISH=false in .env (caution!)
    python scripts/run_single_job.py --publish
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import ensure_db_tables, get_session, init_db
from app.gemini.client import GeminiClient
from app.logging_config import setup_logging
from app.models import JobStage, JobStatus, TopicCategory, VideoJob
from app.pipeline import VideoPipeline
from app.quota_manager import QuotaManager
from app.services.job_service import JobService
from app.topic_manager import TopicManager
from app.video.asset_storage import AssetStorage


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run a single video creation job")
    parser.add_argument("--topic", type=str, default=None, help="Specific topic in Hindi or English")
    parser.add_argument("--category", type=str, default=None, choices=[c.value for c in TopicCategory], help="Topic category")
    parser.add_argument("--dry-run", action="store_true", help="Generate assets but skip YouTube upload")
    parser.add_argument("--publish", action="store_true", help="Publish to YouTube (overrides settings.auto_publish)")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)
    logger = logging.getLogger("run_single_job")

    # Initialize local SQLite or PostgreSQL database
    init_db(settings.database_url)
    await ensure_db_tables()

    print("=" * 60)
    print("Auto Shorts - Single Job Execution")
    print("=" * 60)

    # Override auto_publish if requested
    if args.dry_run:
        settings.auto_publish = False
        print("[*] Dry run active: YouTube upload will be skipped.")
    elif args.publish:
        settings.auto_publish = True
        print("[!] Force publish active: Video will be uploaded to YouTube.")

    if not settings.gemini_api_key or "your_free_gemini" in settings.gemini_api_key:
        print("\n[!] GEMINI_API_KEY is not configured yet in .env!")
        print("    1. Open .env in your editor.")
        print("    2. Get a free API key at: https://aistudio.google.com/app/apikey")
        print("    3. Set GEMINI_API_KEY=AIzaSy... and run again.\n")
        sys.exit(1)

    gemini_client = GeminiClient(
        api_key=settings.gemini_api_key,
        text_model=settings.gemini_text_model,
        video_model=settings.gemini_video_model,
    )
    storage = AssetStorage(settings)

    job_id: int | None = None

    async with await get_session() as session:
        topic_mgr = TopicManager(session)
        job_svc = JobService(session)

        # Determine topic
        if args.topic:
            cat = TopicCategory(args.category) if args.category else TopicCategory.DEITY
            selected_topic, created = await topic_mgr.get_or_create_topic(
                topic_text=args.topic,
                category=cat,
            )
            print(f"[+] Using specified topic: {selected_topic.topic_text} ({selected_topic.category.value})")
        else:
            await topic_mgr.seed_topics()
            unused = await topic_mgr.get_unused_topics(limit=1)
            if not unused:
                print("[-] No unused topics found in database.")
                sys.exit(1)
            selected_topic = unused[0]
            print(f"[+] Selected topic from DB: {selected_topic.topic_text} ({selected_topic.category.value})")

        # Create or retrieve job
        job = await job_svc.create_job(selected_topic)
        if job.status in (JobStatus.FAILED, JobStatus.RUNNING):
            job.status = JobStatus.PENDING
            job.stage = JobStage.TOPIC_SELECTED
            job.error_details = None
        await session.commit()
        job_id = job.id
        print(f"[+] VideoJob ready: id={job.id}")

    # Run the pipeline in its own session
    print("[*] Starting pipeline execution...")
    async with await get_session() as session:
        quota_mgr = QuotaManager(session, settings)
        pipeline = VideoPipeline(
            session=session,
            settings=settings,
            gemini_client=gemini_client,
            quota_manager=quota_mgr,
            storage=storage,
        )
        success = await pipeline.run_job(job_id)

    if success:
        async with await get_session() as session:
            from sqlalchemy import select
            res = await session.execute(select(VideoJob).where(VideoJob.id == job_id))
            job = res.scalar_one()
            print("=" * 60)
            print(f"[SUCCESS] Job {job.id} completed!")
            print(f"Status: {job.status.value}")
            if job.stage:
                print(f"Final Stage: {job.stage.value}")
            print("=" * 60)
    else:
        async with await get_session() as session:
            from sqlalchemy import select
            res = await session.execute(select(VideoJob).where(VideoJob.id == job_id))
            job = res.scalar_one()
            print("=" * 60)
            print(f"[FAILED] Job {job.id} failed.")
            print(f"Failure Category: {job.failure_category.value if job.failure_category else 'Unknown'}")
            print(f"Error Details: {job.error_details}")
            print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
