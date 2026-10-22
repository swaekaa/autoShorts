"""
Tests: Narration Generator (mocked Edge TTS and Google Cloud TTS)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.audio.narration import NarrationGenerator


def make_settings(tts_provider="edge"):
    s = MagicMock()
    s.tts_provider = tts_provider
    s.tts_voice_name = "hi-IN-MadhurNeural"
    s.tts_speaking_rate = 1.1
    s.tts_language_code = "hi-IN"
    return s


@pytest.mark.asyncio
async def test_edge_tts_synthesize_with_mock(tmp_path):
    output_path = tmp_path / "narration.aac"
    settings = make_settings(tts_provider="edge")
    quota_mgr = MagicMock()

    generator = NarrationGenerator(settings=settings, quota_manager=quota_mgr)

    with (
        patch("edge_tts.Communicate") as mock_comm_cls,
        patch("app.audio.narration.get_ffmpeg_path", return_value="ffmpeg"),
        patch("subprocess.run") as mock_subproc,
        patch.object(generator, "_get_audio_duration", return_value=8.5),
    ):
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        mock_comm_cls.return_value = mock_comm

        # Mock ffmpeg convert to aac
        def fake_ffmpeg(cmd, **kwargs):
            aac_target = Path(cmd[-1])
            aac_target.write_bytes(b"fake aac audio data")
            return MagicMock(returncode=0)

        mock_subproc.side_effect = fake_ffmpeg

        res_path, duration = await generator.synthesize(
            text="भगवान शिव की स्तुति",
            output_path=output_path,
        )

        assert res_path.exists()
        assert duration == 8.5
        mock_comm.save.assert_called_once()
