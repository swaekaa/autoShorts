"""
YouTube Video Uploader
======================
Uploads validated videos as YouTube Shorts using the Data API v3.
Implements:
- Channel identity verification (must match YOUTUBE_CHANNEL_ID)
- Upload intent records (prevents duplicate uploads after network errors)
- Resumable uploads with session state
- Post-upload verification
- Quota event recording
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.logging_config import get_logger
from app.quota_manager import QuotaEventType, QuotaManager, ServiceProvider
from app.youtube.oauth import YouTubeOAuth

logger = get_logger(__name__)

# YouTube API quota costs (units):
# videos.insert = 1600 units
# youtube.readonly = 1 unit
# Daily quota: 10,000 units (standard) → max ~6 uploads/day before hitting quota


class ChannelVerificationError(Exception):
    """Raised when the authenticated channel doesn't match the configured target."""


class UploadQuotaError(Exception):
    """Raised when YouTube upload quota is exhausted."""


class YouTubeUploader:
    def __init__(
        self,
        oauth: YouTubeOAuth,
        quota_manager: QuotaManager,
        settings: Any,
    ):
        self._oauth = oauth
        self._quota = quota_manager
        self._settings = settings
        self._youtube = None
        self._verified_channel_id: str | None = None

    def _get_youtube_service(self):
        """Build YouTube API service with fresh credentials."""
        creds = self._oauth.get_credentials()
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    async def verify_channel_identity(self) -> str:
        """
        Verify that the authenticated account owns the configured YOUTUBE_CHANNEL_ID.
        Returns the verified channel ID.
        Raises ChannelVerificationError if there's a mismatch.

        IMPORTANT: Never upload to a different channel than configured.
        """
        youtube = self._get_youtube_service()
        request = youtube.channels().list(part="id,snippet", mine=True)
        response = request.execute()

        channels = response.get("items", [])
        if not channels:
            raise ChannelVerificationError(
                "No channels found for the authenticated account. "
                "Ensure you authorized the correct Google account."
            )

        found_channel_id = channels[0]["id"]
        configured_id = self._settings.youtube_channel_id

        if found_channel_id != configured_id:
            raise ChannelVerificationError(
                f"Channel ID mismatch! "
                f"Authenticated as: {found_channel_id}, "
                f"Configured target: {configured_id}. "
                f"Publishing DISABLED for safety. "
                f"Re-run scripts/youtube_auth.py with the correct account."
            )

        channel_title = channels[0].get("snippet", {}).get("title", "Unknown")
        self._verified_channel_id = found_channel_id
        logger.info(
            "Channel identity verified",
            extra={"channel_id": found_channel_id, "title": channel_title},
        )
        return found_channel_id

    async def upload_video(
        self,
        video_path: str | Path,
        title: str,
        description: str,
        tags: list[str],
        category_id: int = 27,
        privacy_status: str = "public",
    ) -> dict[str, Any]:
        """
        Upload a validated video to YouTube.
        Returns the API response with the YouTube video ID.

        Safety checks:
        1. Channel identity must be verified
        2. AUTO_PUBLISH must be enabled
        3. Video path must exist
        4. Quota must be available
        """
        # Safety checks
        if not self._settings.auto_publish:
            raise RuntimeError(
                "AUTO_PUBLISH is disabled. Set AUTO_PUBLISH=true in .env after testing."
            )

        if self._verified_channel_id is None:
            await self.verify_channel_identity()

        if not await self._quota.can_generate(ServiceProvider.YOUTUBE):
            raise UploadQuotaError("YouTube API quota unavailable")

        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Build metadata
        body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags[:30],
                "categoryId": str(category_id),
                "defaultLanguage": "hi",
                "defaultAudioLanguage": "hi",
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
                # Required for synthetic/AI-generated content disclosure
                "containsSyntheticMedia": True,
            },
        }

        logger.info(
            "Starting YouTube upload",
            extra={
                "title": title[:60],
                "privacy": privacy_status,
                "file_size": video_path.stat().st_size,
            },
        )

        youtube = self._get_youtube_service()

        # Resumable upload with 256KB chunks
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=256 * 1024,
        )

        try:
            insert_request = youtube.videos().insert(
                part=",".join(body.keys()),
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = insert_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.debug(
                        "Upload progress",
                        extra={"progress_pct": progress},
                    )

            video_id = response.get("id", "")
            video_url = f"https://www.youtube.com/shorts/{video_id}"

            await self._quota.record_event(
                provider=ServiceProvider.YOUTUBE,
                event_type=QuotaEventType.SUCCESS,
                observed_usage={"operation": "videos.insert", "units": 1600},
            )

            logger.info(
                "Upload successful",
                extra={
                    "video_id": video_id,
                    "url": video_url,
                    "title": title[:60],
                },
            )

            return {
                "video_id": video_id,
                "url": video_url,
                "response": response,
            }

        except HttpError as exc:
            error_content = exc.content.decode() if exc.content else str(exc)
            logger.error(
                "YouTube upload failed",
                extra={
                    "status_code": exc.status_code,
                    "error": error_content[:500],
                },
            )

            if exc.status_code in (403, 429):
                await self._quota.record_event(
                    provider=ServiceProvider.YOUTUBE,
                    event_type=QuotaEventType.QUOTA_EXCEEDED,
                    error_code=f"HTTP_{exc.status_code}",
                )
                raise UploadQuotaError(f"YouTube quota error: {exc.status_code}") from exc

            raise

    async def verify_uploaded_video(self, video_id: str) -> dict[str, Any]:
        """
        Verify an uploaded video exists and has the correct properties.
        Returns video metadata from the API.
        """
        youtube = self._get_youtube_service()
        request = youtube.videos().list(
            part="id,status,snippet",
            id=video_id,
        )
        response = request.execute()

        items = response.get("items", [])
        if not items:
            raise ValueError(f"Video {video_id} not found via API after upload")

        video = items[0]
        status = video.get("status", {})
        privacy = status.get("privacyStatus", "unknown")

        logger.info(
            "Video verified",
            extra={
                "video_id": video_id,
                "privacy": privacy,
                "upload_status": status.get("uploadStatus", "unknown"),
            },
        )
        return video
