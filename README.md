# Autonomous Hindu Educational YouTube Shorts Factory (100% Free Tier)

A production-ready automation service that autonomously creates and publishes high-retention educational Hindu religion and mythology YouTube Shorts to your YouTube channel.

**100% Free Tier & Zero-Docker Architecture**: Operates with $0.00 infrastructure cost, requiring no credit card, no cloud database, and no Docker installation.

---

## Table of Contents
1. [Free Tier Architecture](#free-tier-architecture)
2. [Why No Docker is Needed](#why-no-docker-is-needed)
3. [Quick Start (Windows / Mac / Linux)](#quick-start)
4. [Free Tier Component Breakdown](#free-tier-component-breakdown)
5. [YouTube OAuth 2.0 Authorization Flow](#youtube-oauth-20-authorization-flow)
6. [Testing & Dry Runs](#testing--dry-runs)
7. [REST API Documentation](#rest-api-documentation)
8. [Configuration Reference](#configuration-reference)

---

## Free Tier Architecture

```
[ Topic Manager ] (Rotates Hindu deities, scriptures, festivals, philosophy)
       │
       ▼
[ Gemini 1.5/2.5 Flash Free Tier ] (Generates Hindi script, Devanagari text & visual prompts)
       │
       ▼
[ Edge Neural TTS ] (100% Free Studio-grade hi-IN-MadhurNeural / hi-IN-SwaraNeural voice)
       │
       ▼
[ Free Motion Visual Engine ] (Generates vertical 9:16 devotional imagery + FFmpeg Ken Burns pan/zoom)
       │
       ▼
[ FFmpeg Subtitle & Audio Mixer ] (Burned-in Devanagari ASS subtitles + ambient audio)
       │
       ▼
[ Media Validator ] (ffprobe strict check: exact 10.0s ±0.1s, 1080x1920, 30fps)
       │
       ▼
[ YouTube Uploader ] (Free Data API v3 quota: 10,000 units/day, synthetic content disclosure)
```

---

## Why No Docker is Needed

* **SQLite Out of the Box**: By default, the service uses `sqlite+aiosqlite:///./auto_shorts.db`. Tables and seed data are created automatically when the app starts. No PostgreSQL server or database container required.
* **Pure Python + FFmpeg**: The entire stack runs as a native Python process with an async background worker loop.
* **Zero Container Overhead**: Low memory footprint (~120MB RAM), fast boot time (<1 second).

---

## Quick Start

### 1. Prerequisites
- **Python 3.11+** installed and in `PATH`.
- **FFmpeg & FFprobe** installed and in `PATH`.
  - Windows: Run `winget install Gyan.FFmpeg` or download from [ffmpeg.org](https://ffmpeg.org/download.html).
  - Ubuntu/Debian: `sudo apt-get install ffmpeg fonts-noto-extra`
  - macOS: `brew install ffmpeg`

### 2. Setup
On Windows, simply run:
```cmd
setup.bat
```
Or manually in terminal:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### 3. Add Free Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey) and generate a **free API key**.
2. Open `.env` and paste:
   ```env
   GEMINI_API_KEY=AIzaSy...
   ```

### 4. Run the Factory
On Windows:
```cmd
run.bat
```
Or via Python:
```bash
python run.py
```
This boots the FastAPI REST API and immediately begins the autonomous creation loop!
- Interactive API Docs: `http://127.0.0.1:8000/docs`
- Healthcheck: `http://127.0.0.1:8000/health`

---

## Free Tier Component Breakdown

| Component | Free Provider | Monthly Cost | Constraints / Quotas |
| :--- | :--- | :--- | :--- |
| **Database** | SQLite (`auto_shorts.db`) | **$0.00** | Zero setup, local file |
| **Script Generation** | Gemini 1.5 Flash (AI Studio) | **$0.00** | 1,500 requests/day, 15 RPM |
| **Hindi Voice (TTS)** | Microsoft Edge Neural TTS | **$0.00** | Unlimited free tier, studio quality |
| **Visual / Video** | Free Motion + FFmpeg Ken Burns | **$0.00** | 1080x1920 30fps vertical video |
| **Audio Mixing** | FFmpeg built-in synthesis | **$0.00** | Local computation |
| **Storage** | Local disk (`./storage/`) | **$0.00** | Stored in local directory |
| **YouTube Upload** | YouTube Data API v3 | **$0.00** | 10,000 units/day (~6 Shorts/day) |

---

## YouTube OAuth 2.0 Authorization Flow

To grant the service permission to upload directly to your YouTube channel:

1. In the [Google Cloud Console](https://console.cloud.google.com/), enable the **YouTube Data API v3**.
2. Create **OAuth 2.0 Credentials** (Application type: *Desktop application*).
3. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.
4. Run the one-time authorization script:
   ```bash
   python scripts/youtube_auth.py
   ```
5. Sign in to your YouTube channel account in the browser pop-up.
6. Copy the generated `YOUTUBE_REFRESH_TOKEN` into `.env`.
7. When you want videos to be uploaded automatically to your channel, change:
   ```env
   AUTO_PUBLISH=true
   ```

---

## Testing & Dry Runs

### Run a Single Video Job (Dry-Run / No Upload)
To test the script generator, voice synthesis, video motion, and subtitles without uploading to YouTube:
```bash
python scripts/run_single_job.py --dry-run
```

### Run for a Specific Hindu Topic
```bash
python scripts/run_single_job.py --topic "भगवान शिव का तीसरा नेत्र" --category deity --dry-run
```

### Run Unit Tests
```bash
pytest -v
```

---

## REST API Documentation

All admin endpoints accept the header `X-Admin-Api-Key: <ADMIN_API_KEY>`.

- `GET /health`: Health status and daily statistics.
- `GET /api/jobs`: List generated and published video jobs.
- `POST /api/jobs/manual`: Submit a custom topic for immediate generation.
- `POST /api/jobs/{job_id}/retry`: Retry an interrupted or failed job.
- `GET /api/settings`: Inspect runtime settings and quota states.
- `POST /api/settings/emergency-stop`: Pause all autonomous operations instantly.
- `POST /api/settings/resume`: Resume autonomous worker loop.

---

## Configuration Reference

Key variables in `.env`:

```env
# AI Studio Free Tier
GEMINI_API_KEY=your_key_here
GEMINI_TEXT_MODEL=gemini-1.5-flash

# Visual & Audio Engines (100% Free)
VISUAL_GENERATOR=free_motion
TTS_PROVIDER=edge
TTS_VOICE_NAME=hi-IN-MadhurNeural

# Database (No Docker required)
DATABASE_URL=sqlite+aiosqlite:///./auto_shorts.db

# Daily Controls
MAX_DAILY_VIDEOS=5
AUTO_PUBLISH=false
```
