"""Core services package.

Each service is a self-contained class that can be unit-tested in isolation.
Services receive their settings via constructor injection — they never read
environment variables directly.
"""
from core.services.db_service import Base, DBService, Document
from core.services.llm_service import (
    Intent,
    Language,
    LLMResponseError,
    LLMService,
)
from core.services.ocr_service import ExtractionResult, OCRService
from core.services.vector_store import SearchHit, VectorStoreService

__all__ = [
    "Base",
    "DBService",
    "Document",
    "ExtractionResult",
    "Intent",
    "LLMResponseError",
    "LLMService",
    "Language",
    "OCRService",
    "SearchHit",
    "VectorStoreService",
]
