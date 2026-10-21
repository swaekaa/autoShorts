"""
Database Migration / Table Setup Runner
========================================
Usage: python scripts/migrate.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import ensure_db_tables, init_db


async def main():
    settings = get_settings()
    init_db(settings.database_url)

    if settings.database_url.startswith("sqlite"):
        print(f"Initializing local SQLite database: {settings.database_url}")
        await ensure_db_tables()
        print("SQLite tables verified and ready.")
    else:
        from alembic import command
        from alembic.config import Config

        print("Applying Alembic migrations for PostgreSQL...")
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        print("Migrations applied successfully.")


if __name__ == "__main__":
    asyncio.run(main())
