"""Cached factory for backend services and compiled LangGraph pipelines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import streamlit as st

from app.async_runner import run_async
from config import settings
from core.pipeline import build_chat_agent, build_doc_pipeline
from core.services import DBService, LLMService, OCRService, VectorStoreService
from rag import LexIngestionService


@dataclass(frozen=True)
class _Services:
    ocr: OCRService
    llm: LLMService
    vector: VectorStoreService
    db: DBService


@st.cache_resource
def get_services() -> _Services:
    """Build once, reuse across all Streamlit reruns."""
    return _Services(
        ocr=OCRService(language="en"),
        llm=LLMService(
            ollama_settings=settings.ollama,
            openai_settings=settings.openai,
            provider=settings.llm_provider,
        ),
        vector=VectorStoreService(settings.qdrant, settings.ollama),
        db=DBService(settings.postgres),
    )


@st.cache_resource
def get_doc_pipeline():
    svc = get_services()
    return build_doc_pipeline(svc.ocr, svc.llm, svc.vector, svc.db)


@st.cache_resource
def get_chat_agent():
    svc = get_services()
    return build_chat_agent(svc.llm, svc.vector, svc.db)


@st.cache_resource
def get_lex_ingestion_service() -> LexIngestionService:
    svc = get_services()
    return LexIngestionService(vector_store=svc.vector)


# ── Sync API for pages ──────────────────────────────────────────────


def process_document(file_path: str) -> dict[str, Any]:
    pipeline = get_doc_pipeline()
    return run_async(pipeline.ainvoke({"file_path": file_path}))


def ask_chat_agent(
    user_input: str,
    *,
    context_doc_ids: list[str] | None = None,
) -> dict[str, Any]:
    agent = get_chat_agent()
    return run_async(agent.ainvoke({
        "user_input": user_input,
        "context_doc_ids": context_doc_ids or [],
    }))


def list_documents(*, doc_type: str | None = None, limit: int = 100) -> list[dict]:
    db = get_services().db
    return run_async(db.list_documents(doc_type=doc_type, limit=limit))


def get_document(doc_id: str) -> dict | None:
    db = get_services().db
    return run_async(db.get_document(doc_id))


def delete_document(doc_id: str) -> None:
    db = get_services().db
    run_async(db.delete_document(doc_id))


def delete_document_full(doc_id: str) -> None:
    """Delete from PostgreSQL AND purge all Qdrant doc_chunks for this doc."""
    svc = get_services()
    run_async(svc.db.delete_document(doc_id))
    run_async(svc.vector.delete_doc_chunks(doc_id))


# ── KB / lex_uz helpers ─────────────────────────────────────────────


def list_lex_sources() -> list[dict]:
    return run_async(get_services().vector.list_lex_sources())


def delete_lex_source(source: str) -> None:
    run_async(get_services().vector.delete_lex_source(source))


def list_doc_chunk_counts() -> dict[str, int]:
    return run_async(get_services().vector.list_doc_chunk_counts())


# ── Database management ─────────────────────────────────────────────


def tables_exist() -> bool:
    return run_async(get_services().db.tables_exist())


def init_db() -> None:
    run_async(get_services().db.create_tables())


def drop_db() -> None:
    run_async(get_services().db.drop_tables())


def ingest_kb_source(source: str | Any):
    service = get_lex_ingestion_service()
    return run_async(service.ingest(source))


# ── Health checks ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class HealthStatus:
    ollama: bool
    qdrant: bool
    postgres: bool

    @property
    def all_healthy(self) -> bool:
        return self.ollama and self.qdrant and self.postgres


def check_health() -> HealthStatus:
    svc = get_services()

    def _ollama_ok() -> bool:
        text = run_async(svc.llm.complete("Reply with just OK.", "ping"))
        return isinstance(text, str) and len(text) > 0

    def _qdrant_ok() -> bool:
        run_async(svc.vector.ensure_collections())
        return True

    def _postgres_ok() -> bool:
        result = run_async(svc.db.list_documents(limit=1))
        return isinstance(result, list)

    return HealthStatus(
        ollama=_safe_check(_ollama_ok),
        qdrant=_safe_check(_qdrant_ok),
        postgres=_safe_check(_postgres_ok),
    )


def _safe_check(fn) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False