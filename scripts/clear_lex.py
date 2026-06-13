"""Wipe the lex_uz collection (use before re-ingesting from scratch).

Drops and recreates the collection, so all previously ingested chunks
are removed. The doc_chunks collection is untouched.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from core.logging import configure_logging, get_logger
from core.services import VectorStoreService

logger = get_logger(__name__)


async def main() -> int:
    configure_logging(settings.log_level)

    vector = VectorStoreService(settings.qdrant, settings.ollama)
    collection = settings.qdrant.lex_collection

    try:
        if not await vector._client.collection_exists(collection):
            logger.info("Collection %r does not exist — nothing to clear.", collection)
            return 0

        logger.warning("Deleting collection %r...", collection)
        await vector._client.delete_collection(collection)
        logger.info("Collection deleted. Recreating empty...")
        await vector.ensure_collections()
        logger.info("Done. Run `python scripts/ingest_lex.py <sources>` to repopulate.")
        return 0
    finally:
        await vector.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
