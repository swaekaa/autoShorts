"""
Tests: YouTube Uploader (mocked Google Data API v3 and OAuth)
"""

from unittest.mock import MagicMock, patch
import pytest

from app.youtube.uploader import (
    ChannelVerificationError,
    UploadQuotaError,
    YouTubeUploader,
)


def make_settings(channel_id="UC_test_channel_123"):
    s = MagicMock()
    s.youtube_channel_id = channel_id
    s.default_video_category_id = 27
    s.video_privacy_status = "public"
    return s


@pytest.mark.asyncio
async def test_verify_channel_identity_matches():
    oauth = MagicMock()
    quota_mgr = MagicMock()
    settings = make_settings(channel_id="UC_exact_match_123")

    uploader = YouTubeUploader(oauth=oauth, quota_manager=quota_mgr, settings=settings)

    mock_service = MagicMock()
    mock_request = MagicMock()
    mock_request.execute.return_value = {
        "items": [
            {
                "id": "UC_exact_match_123",
                "snippet": {"title": "Sacred Shorts Channel"},
            }
        ]
    }
    mock_service.channels().list.return_value = mock_request

    with patch.object(uploader, "_get_youtube_service", return_value=mock_service):
        verified_id = await uploader.verify_channel_identity()
        assert verified_id == "UC_exact_match_123"


@pytest.mark.asyncio
async def test_verify_channel_identity_mismatch_raises_error():
    oauth = MagicMock()
    quota_mgr = MagicMock()
    settings = make_settings(channel_id="UC_configured_channel")

    uploader = YouTubeUploader(oauth=oauth, quota_manager=quota_mgr, settings=settings)

    mock_service = MagicMock()
    mock_request = MagicMock()
    mock_request.execute.return_value = {
        "items": [
            {
                "id": "UC_different_channel",
                "snippet": {"title": "Wrong Channel"},
            }
        ]
    }
    mock_service.channels().list.return_value = mock_request

    with patch.object(uploader, "_get_youtube_service", return_value=mock_service):
        with pytest.raises(ChannelVerificationError, match="Channel ID mismatch"):
            await uploader.verify_channel_identity()
