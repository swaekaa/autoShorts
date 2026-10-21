FROM python:3.11-slim-bullseye AS base

# Install system dependencies
# ffmpeg: required for video rendering, ffprobe validation, audio mixing
# fonts-noto-core & fonts-noto-extra: includes Noto Sans Devanagari for rendering Hindi text
# libpq-dev, build-essential: for PostgreSQL client compilation if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-core \
    fonts-noto-extra \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-privileged user and storage directories
RUN groupadd -r autoshorts && useradd -r -g autoshorts autoshorts && \
    mkdir -p /app/storage/generated /app/storage/music /app/storage/logs && \
    chown -R autoshorts:autoshorts /app

# Copy application source code
COPY --chown=autoshorts:autoshorts alembic.ini .
COPY --chown=autoshorts:autoshorts migrations ./migrations
COPY --chown=autoshorts:autoshorts scripts ./scripts
COPY --chown=autoshorts:autoshorts app ./app

# Switch to non-root user
USER autoshorts

# Expose FastAPI port
EXPOSE 8000

# Default command: run database migration then launch FastAPI + autonomous worker
CMD ["sh", "-c", "python scripts/migrate.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
