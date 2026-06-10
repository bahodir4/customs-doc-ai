"""Initialise the PostgreSQL schema.

Run once after `docker compose up -d`:
    python scripts/init_db.py

Idempotent — re-running is safe.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from core.logging import configure_logging, get_logger
from core.services import DBService

logger = get_logger(__name__)


async def main() -> int:
    configure_logging(settings.log_level)
    logger.info("Initialising database schema...")

    db = DBService(settings.postgres)
    try:
        await db.create_tables()
    finally:
        await db.close()

    logger.info("Schema ready.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
