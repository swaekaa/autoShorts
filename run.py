"""
Auto Shorts - Local Service Launcher (No Docker Required)
=========================================================
Runs the FastAPI API server and background autonomous worker locally
using SQLite and 100% Free Tier providers.

Usage:
    python run.py
"""

from __future__ import annotations

import logging
import sys
import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()

    print("=" * 65)
    print("  AUTONOMOUS HINDU SHORTS FACTORY (100% FREE TIER)")
    print("=" * 65)
    print(f" Database:         {settings.database_url}")
    print(f" Text Model:       {settings.gemini_text_model} (Google AI Studio Free Tier)")
    print(f" TTS Engine:       {settings.tts_provider} ({settings.tts_voice_name}) (100% Free)")
    print(f" Visual Engine:    {settings.visual_generator} (100% Free)")
    print(f" Auto Publish:     {settings.auto_publish}")
    print(f" Server Port:      http://{settings.api_host}:{settings.api_port}")
    print(f" Swagger Docs:     http://{settings.api_host}:{settings.api_port}/docs")
    print("=" * 65)
    print("Starting background worker and API server... (Press Ctrl+C to exit)\n")

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
