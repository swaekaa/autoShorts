"""
Tests: Media Validator
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.media.validator import MediaValidator
from app.schemas import ValidationResult


def make_settings(
    duration=10,
    width=1080,
    height=1920,
    fps=30,
    video_codec="libx264",
    audio_codec="aac",
):
    s = MagicMock()
    s.video_duration_seconds = duration
    s.video_width = width
    s.video_height = height
    s.video_fps = fps
    s.expected_video_frames = duration * fps
    return s


VALID_FFPROBE_OUTPUT = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1080,
            "height": 1920,
            "r_frame_rate": "30/1",
            "nb_frames": "300",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
        },
    ],
    "format": {
        "duration": "10.000000",
        "size": "5000000",
    },
}


def mock_ffprobe_success(probe_data: dict):
    """Return a subprocess mock that outputs given probe data."""
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(probe_data)
    mock.stderr = ""
    return mock


@pytest.fixture
def tmp_video(tmp_path):
    """Create a fake video file of sufficient size."""
    p = tmp_path / "test_video.mp4"
    p.write_bytes(b"0" * 500_000)  # 500KB fake
    return p


def test_valid_video_passes(tmp_video):
    with (
        patch("subprocess.run") as mock_run,
    ):
        mock_run.side_effect = [
            mock_ffprobe_success(VALID_FFPROBE_OUTPUT),  # ffprobe call
            MagicMock(returncode=0),  # decodability check
        ]
        validator = MediaValidator(make_settings())
        result = validator.validate(tmp_video)
    assert result.passed is True
    assert result.duration_seconds == 10.0
    assert result.width == 1080
    assert result.height == 1920
    assert result.has_audio is True


def test_wrong_duration_fails(tmp_video):
    probe = dict(VALID_FFPROBE_OUTPUT)
    probe["format"] = {"duration": "8.500000"}  # Wrong duration
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            mock_ffprobe_success(probe),
            MagicMock(returncode=0),
        ]
        validator = MediaValidator(make_settings())
        result = validator.validate(tmp_video)
    assert result.passed is False
    assert any("Duration" in e for e in result.errors)


def test_wrong_resolution_fails(tmp_video):
    probe = dict(VALID_FFPROBE_OUTPUT)
    probe["streams"] = [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,  # Wrong – horizontal
            "height": 1080,
            "r_frame_rate": "30/1",
            "nb_frames": "300",
        },
        {"codec_type": "audio", "codec_name": "aac"},
    ]
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            mock_ffprobe_success(probe),
            MagicMock(returncode=0),
        ]
        validator = MediaValidator(make_settings())
        result = validator.validate(tmp_video)
    assert result.passed is False
    assert any("Width" in e or "Height" in e for e in result.errors)


def test_missing_audio_fails(tmp_video):
    probe = dict(VALID_FFPROBE_OUTPUT)
    probe["streams"] = [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1080,
            "height": 1920,
            "r_frame_rate": "30/1",
            "nb_frames": "300",
        }
        # No audio stream
    ]
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            mock_ffprobe_success(probe),
            MagicMock(returncode=0),
        ]
        validator = MediaValidator(make_settings())
        result = validator.validate(tmp_video)
    assert result.passed is False
    assert any("audio" in e.lower() for e in result.errors)


def test_file_not_found_fails():
    validator = MediaValidator(make_settings())
    result = validator.validate("/nonexistent/path/video.mp4")
    assert result.passed is False
    assert any("not exist" in e for e in result.errors)


def test_decodability_failure_fails(tmp_video):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            mock_ffprobe_success(VALID_FFPROBE_OUTPUT),
            MagicMock(returncode=1, stderr="decode error"),  # Decode fails
        ]
        validator = MediaValidator(make_settings())
        result = validator.validate(tmp_video)
    assert result.passed is False
    assert any("decodability" in e.lower() for e in result.errors)
