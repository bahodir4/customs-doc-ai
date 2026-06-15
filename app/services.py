"""Cached factory for backend services and compiled LangGraph pipelines."""
from __future__ import annotations

import asyncio
import queue as _queue
from dataclasses import dataclass
from typing import Any, Generator

import streamlit as st

from app.async_runner import run_async, stream_async, submit_to_loop
from config import settings
from core.pipeline import build_chat_agent, build_doc_pipeline, build_retrieval_pipeline
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
def get_retrieval_pipeline():
    """Retrieval-only pipeline: detect language/intent + fetch context, no LLM response."""
    svc = get_services()
    return build_retrieval_pipeline(svc.llm, svc.vector, svc.db)


@st.cache_resource
def get_lex_ingestion_service() -> LexIngestionService:
    svc = get_services()
    backup_dir = settings.project_root / "docs" / "lex_uz" / "converted"
    return LexIngestionService(vector_store=svc.vector, markdown_backup_dir=backup_dir)


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


def stream_chat_agent(
    user_input: str,
    *,
    context_doc_ids: list[str] | None = None,
    meta_out: dict,
):
    """Sync generator that streams the assistant response token by token.

    Runs the retrieval pipeline (language detection + intent + retrieval) as a
    single async call, then streams the final LLM response via astream_chat().

    ``meta_out`` is populated in-place with ``language``, ``intent``, and
    ``sources`` once retrieval completes — before the first token is yielded.
    """
    # Resolve @st.cache_resource objects HERE on the main Streamlit thread so
    # the background event-loop thread never calls into Streamlit's caching
    # machinery (which requires a ScriptRunContext and would emit warnings).
    _pipeline = get_retrieval_pipeline()
    _llm = get_services().llm

    async def _astream():
        # Phase 1: detect language/intent and retrieve context (fast, no streaming)
        state = await _pipeline.ainvoke({
            "user_input": user_input,
            "context_doc_ids": context_doc_ids or [],
        })
        meta_out["language"] = state.get("detected_language", "en")
        meta_out["intent"] = state.get("intent")
        meta_out["sources"] = state.get("sources_used", [])

        # Phase 2: stream final response token by token
        async for token in _llm.astream_chat(
            question=user_input,
            context=state.get("context", "(no context retrieved)"),
            language=meta_out["language"],
        ):
            yield token

    return stream_async(_astream)


_DOC_NODES = frozenset({"load", "ocr", "classify", "extract", "store"})
_DOC_SKIP_FIELDS = frozenset({"raw_text"})  # too large to relay to UI


def stream_doc_pipeline(
    file_path: str,
) -> Generator[tuple[str, dict], None, None]:
    """Sync generator: yields ``(node_name, output_dict)`` as each pipeline stage completes.

    Runs the doc pipeline via LangGraph ``astream_events`` on the background
    event loop and relays node-completion events to the Streamlit thread via a
    ``queue.Queue``.  Large fields (``raw_text``) are stripped from the output
    so only UI-relevant metadata is passed.
    """
    _pipeline = get_doc_pipeline()
    q: _queue.Queue = _queue.Queue()
    _DONE = object()

    async def _run() -> None:
        try:
            async for event in _pipeline.astream_events(
                {"file_path": file_path}, version="v2"
            ):
                if event.get("event") == "on_chain_end":
                    node = event.get("metadata", {}).get("langgraph_node")
                    if node in _DOC_NODES:
                        raw_out = event.get("data", {}).get("output") or {}
                        summary = {k: v for k, v in raw_out.items() if k not in _DOC_SKIP_FIELDS}
                        q.put((node, summary))
            q.put(_DONE)
        except Exception as exc:  # noqa: BLE001
            q.put(exc)

    submit_to_loop(_run())

    while True:
        item = q.get(timeout=300)
        if item is _DONE:
            return
        if isinstance(item, BaseException):
            raise item
        yield item


def stream_kb_ingest(source: Any) -> Generator[tuple[str, dict], None, None]:
    """Sync generator: yields ``(stage, data)`` tuples as KB ingestion progresses.

    Stages (in order): ``converting`` → ``converted`` → ``chunking`` →
    ``chunked`` → ``embedding`` → ``stored`` → ``done``.
    """
    _svc = get_lex_ingestion_service()
    q: _queue.Queue = _queue.Queue()
    _DONE = object()

    def _callback(stage: str, data: Any) -> None:
        q.put((stage, data))

    async def _run() -> None:
        try:
            result = await _svc.ingest(source, progress_callback=_callback)
            q.put(("done", {
                "chunks_written": result.chunks_written,
                "raw_markdown_chars": result.raw_markdown_chars,
                "source": result.source,
                "source_type": result.source_type,
            }))
        except Exception as exc:  # noqa: BLE001
            q.put(exc)
        finally:
            q.put(_DONE)

    submit_to_loop(_run())

    while True:
        item = q.get(timeout=300)
        if item is _DONE:
            return
        if isinstance(item, BaseException):
            raise item
        yield item


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