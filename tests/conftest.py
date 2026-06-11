"""Shared pytest fixtures and configuration.

Tests are split implicitly into two kinds:

- **Unit-style smoke tests** — exercise pure logic (JSON parsing, language
  detection fallbacks) without hitting external services. Run by default.
- **Integration smoke tests** — marked with `@pytest.mark.integration`,
  require Qdrant, PostgreSQL, and Ollama running. Skipped by default;
  enable with `pytest --run-integration`.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from config import settings
from core.logging import configure_logging
from core.services import DBService, LLMService, OCRService, VectorStoreService

SAMPLES_DIR = Path(__file__).parent / "samples"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run tests that require live services (Qdrant, Postgres, Ollama).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: requires running Qdrant, Postgres, and Ollama.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    skip_integration = pytest.mark.skip(
        reason="integration test — pass --run-integration to enable"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


# ── Session setup ────────────────────────────────────────────────────


@pytest.fixture(scope="session", autouse=True)
def _configure_logging() -> None:
    configure_logging("INFO")


# Note: pytest-asyncio manages the event loop on its own. We used to
# redefine `event_loop` here as session-scoped — that pattern is deprecated
# and causes "no current event loop" errors because async clients
# (AsyncQdrantClient, asyncpg) bind to whatever loop they were created on.
# All async fixtures below are function-scoped (the default), matching the
# test's loop.


# ── Service fixtures ────────────────────────────────────────────────


@pytest.fixture
def ocr_service() -> OCRService:
    return OCRService(language="en")


@pytest.fixture
def llm_service() -> LLMService:
    return LLMService(settings.ollama)


@pytest_asyncio.fixture
async def vector_store() -> VectorStoreService:
    svc = VectorStoreService(settings.qdrant, settings.ollama)
    try:
        yield svc
    finally:
        await svc.close()


@pytest_asyncio.fixture
async def db_service() -> DBService:
    svc = DBService(settings.postgres)
    try:
        await svc.create_tables()
        yield svc
    finally:
        await svc.close()


# ── Sample document fixtures ────────────────────────────────────────


@pytest.fixture
def sample_pdf_path() -> Path:
    candidates = sorted(SAMPLES_DIR.glob("*.pdf")) + sorted(SAMPLES_DIR.glob("*.PDF"))
    if not candidates:
        pytest.skip(f"No sample PDF in {SAMPLES_DIR}")
    return candidates[0]


@pytest.fixture
def sample_image_path() -> Path:
    candidates = sorted(SAMPLES_DIR.glob("*.jpg")) + sorted(SAMPLES_DIR.glob("*.png"))
    if not candidates:
        pytest.skip(f"No sample image in {SAMPLES_DIR}")
    return candidates[0]