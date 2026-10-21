@echo off
title Auto Shorts Launcher
echo =========================================================
echo Starting Autonomous Hindu Shorts Factory (Free Tier)
echo =========================================================
if not exist ".env" (
    echo [.env not found!] Creating .env from .env.example...
    copy .env.example .env
    echo Please make sure to add your GEMINI_API_KEY to .env!
)

python run.py
pause
