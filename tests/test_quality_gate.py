"""
Tests: Quality Gate Module
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.media.quality_gate import QualityGate


def make_settings(
    duration=10,
    width=1080,
    height=1920,
    fps=30,
):
    s = MagicMock()
    s.video_duration_seconds = duration
    s.video_width = width
    s.video_height = height
    s.video_fps = fps
    return s


VALID_PROBE_10S = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1080,
            "height": 1920,
            "r_frame_rate": "30/1",
            "nb_frames": "300",
            "duration": "10.000000",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "duration": "10.000000",
        },
    ],
    "format": {
        "duration": "10.000000",
        "size": "3500000",
    },
}

BROKEN_CLIP_2_5S = {
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1080,
            "height": 1920,
            "r_frame_rate": "30/1",
            "nb_frames": "75",
            "duration": "2.500000",
        },
        {
            "codec_type": "audio",
            "codec_name": "aac",
            "duration": "2.500000",
        },
    ],
    "format": {
        "duration": "2.500000",
        "size": "450000",
    },
}


def mock_ffprobe_response(probe_dict):
    mock = MagicMock()
    mock.returncode = 0
    mock.stdout = json.dumps(probe_dict)
    mock.stderr = ""
    return mock


def test_quality_gate_passes_valid_10s_video(tmp_path):
    video_file = tmp_path / "valid_video.mp4"
    video_file.write_bytes(b"0" * 300_000)

    sub_file = tmp_path / "subtitles.ass"
    sub_file.write_text(
        "[Script Info]\nTitle: Test\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n[Events]\nFormat: Layer, Start, End, Style, Text\nDialogue: 0,0:00:00.00,0:00:10.00,Default,Test Subtitle",
        encoding="utf-8",
    )

    gate = QualityGate(make_settings())

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            mock_ffprobe_response(VALID_PROBE_10S),  # ffprobe
            MagicMock(returncode=0),  # decodability check
        ]
        with patch.object(gate, "_verify_scene_diversity", return_value=True):
            res = gate.inspect_video(video_file, subtitle_path=sub_file)

    assert res.passed is True
    assert res.duration_seconds == 10.0
    assert res.width == 1080
    assert res.height == 1920
    assert res.has_audio is True
    assert len(res.errors) == 0


def test_quality_gate_rejects_2_5s_clip(tmp_path):
    video_file = tmp_path / "broken_clip_4.mp4"
    video_file.write_bytes(b"0" * 200_000)

    gate = QualityGate(make_settings())

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            mock_ffprobe_response(BROKEN_CLIP_2_5S),  # ffprobe shows 2.5s
            MagicMock(returncode=0),
        ]
        with patch.object(gate, "_verify_scene_diversity", return_value=True):
            res = gate.inspect_video(video_file)

    assert res.passed is False
    assert any("Duration out of bounds" in e for e in res.errors)
    assert any("Insufficient frames" in e for e in res.errors)


def test_quality_gate_rejects_missing_audio(tmp_path):
    video_file = tmp_path / "silent_video.mp4"
    video_file.write_bytes(b"0" * 200_000)

    probe_no_audio = dict(VALID_PROBE_10S)
    probe_no_audio["streams"] = [probe_no_audio["streams"][0]]  # remove audio stream

    gate = QualityGate(make_settings())

    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = [
            mock_ffprobe_response(probe_no_audio),
            MagicMock(returncode=0),
        ]
        with patch.object(gate, "_verify_scene_diversity", return_value=True):
            res = gate.inspect_video(video_file)

    assert res.passed is False
    assert any("Missing audio stream" in e for e in res.errors)
