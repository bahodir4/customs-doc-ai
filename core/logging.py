"""Logging configuration.

A single `configure_logging()` entry point that any script, test, or
Streamlit app can call once at startup. After that, every module uses
`logging.getLogger(__name__)` and gets a properly formatted logger.

Never call `logging.basicConfig()` directly elsewhere.
"""
from __future__ import annotations

import logging
import sys
from typing import Final

_LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(levelname)-7s | %(name)-32s | %(message)s"
)
_DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"

_configured: bool = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logger. Idempotent — safe to call multiple times."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Quiet down noisy third-party libraries.
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper — equivalent to `logging.getLogger(name)`."""
    return logging.getLogger(name)
