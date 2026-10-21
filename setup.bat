@echo off
title Auto Shorts Setup
echo =========================================================
echo Setting up Auto Shorts Environment (Free Tier, No Docker)
echo =========================================================
echo 1. Checking Python...
python --version
if errorlevel 1 (
    echo Python is not installed or not in PATH! Please install Python 3.11+.
    pause
    exit /b 1
)

echo.
echo 2. Installing Python dependencies...
pip install -r requirements.txt

echo.
echo 3. Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARNING] ffmpeg is not found in PATH!
    echo Please install FFmpeg (e.g. winget install Gyan.FFmpeg or download from ffmpeg.org)
) else (
    echo FFmpeg is installed and ready.
)

if not exist ".env" (
    copy .env.example .env
    echo Created .env from .env.example.
)

echo.
echo =========================================================
echo Setup complete! Now add your GEMINI_API_KEY to .env and run run.bat.
echo =========================================================
pause
