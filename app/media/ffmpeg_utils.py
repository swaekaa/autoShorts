"""
FFmpeg Utility Helper
=====================
Locates the FFmpeg / FFprobe executable on Windows, Linux, and macOS.
Falls back to imageio-ffmpeg if installed or common Windows paths.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def get_ffmpeg_path() -> str:
    """Find ffmpeg binary. Returns path or 'ffmpeg'."""
    # 1. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 2. Check imageio-ffmpeg if available
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if os.path.exists(exe):
            return exe
    except ImportError:
        pass

    # 3. Check common Windows installation locations
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
        os.path.expandvars(r"%USERPROFILE%\ffmpeg\bin\ffmpeg.exe"),
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p

    return "ffmpeg"


def get_ffprobe_path() -> str:
    """Find ffprobe binary. Returns path or 'ffprobe'."""
    found = shutil.which("ffprobe")
    if found:
        return found

    ffmpeg = get_ffmpeg_path()
    if ffmpeg and ffmpeg != "ffmpeg":
        probe_candidate = Path(ffmpeg).parent / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if probe_candidate.exists():
            return str(probe_candidate)

    return "ffprobe"
