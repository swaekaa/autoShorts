"""
FastAPI Application Entry Point
================================
Starts the API server and spawns the background worker.
"""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, jobs, settings
from app.config import get_settings
from app.database import init_db
from app.logging_config import configure_logging


def create_app() -> FastAPI:
    cfg = get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(
        title="Hindu Shorts Factory",
        description="Autonomous Hindu educational YouTube Shorts generation service",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(settings.router)

    @app.on_event("startup")
    async def on_startup():
        cfg = get_settings()
        init_db(cfg.database_url)
        from app.database import ensure_db_tables
        await ensure_db_tables()
        logging.getLogger(__name__).info("Database initialized and verified")

        # Start background worker
        asyncio.create_task(_run_worker(cfg))
        health.set_worker_running(True)

    @app.on_event("shutdown")
    async def on_shutdown():
        health.set_worker_running(False)
        logging.getLogger(__name__).info("API shutdown")

    return app


async def _run_worker(settings) -> None:
    """Background task that runs the autonomous worker."""
    from app.worker import Worker
    worker = Worker(settings)
    try:
        await worker.run()
    except Exception as exc:
        logging.getLogger(__name__).exception(
            "Worker crashed", extra={"error": str(exc)}
        )
        health.set_worker_running(False)


app = create_app()


if __name__ == "__main__":
    cfg = get_settings()
    uvicorn.run(
        "app.main:app",
        host=cfg.api_host,
        port=cfg.api_port,
        log_config=None,  # Use our JSON logger
        reload=False,
    )
