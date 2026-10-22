"""
Tests: Video Renderer (mocked FFmpeg subtitle and video assembly)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.media.renderer import VideoRenderer


def make_settings():
    s = MagicMock()
    s.video_width = 1080
    s.video_height = 1920
    s.video_fps = 30
    s.video_duration_seconds = 10
    s.video_codec = "libx264"
    s.audio_codec = "aac"
    return s


def test_render_final_video_invokes_ffmpeg_with_cwd(tmp_path):
    renderer = VideoRenderer(make_settings())

    raw_video = tmp_path / "raw.mp4"
    raw_video.write_bytes(b"fake video")
    narration = tmp_path / "narration.aac"
    narration.write_bytes(b"fake audio")
    bg_music = tmp_path / "bg.aac"
    bg_music.write_bytes(b"fake music")
    subtitles = tmp_path / "subtitles.ass"
    subtitles.write_text("[Script Info]\n", encoding="utf-8")
    output_video = tmp_path / "final.mp4"

    with patch("subprocess.run") as mock_run:
        def fake_ffmpeg(cmd, **kwargs):
            output_video.write_bytes(b"0" * 20_000)
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            return mock_proc

        mock_run.side_effect = fake_ffmpeg

        result = renderer.render_final_video(
            raw_video_path=raw_video,
            narration_audio_path=narration,
            background_music_path=bg_music,
            subtitle_path=subtitles,
            output_path=output_video,
            narration_duration=8.5,
        )

        assert result == output_video
        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        # Verify cwd was set to the subtitle file's parent directory
        assert kwargs.get("cwd") == str(tmp_path.resolve())
        # Verify subtitle filter used relative filename to avoid Windows path issues
        cmd = args[0]
        cmd_str = " ".join(cmd)
        assert "subtitles=subtitles.ass" in cmd_str
