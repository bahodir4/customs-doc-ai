"""Chat agent graph.

A LangGraph state machine: detect_language → detect_intent → [route] → respond.

The router branches on intent:
  doc_qa  → retrieve_doc_qa   (PostgreSQL fields + doc_chunks semantic)
  rag     → retrieve_rag      (lex_uz customs-law chunks)
  hybrid  → retrieve_hybrid   (all three sources merged)

All retrieval paths converge to `respond`, which assembles the context
and calls the LLM in the user's detected language.
"""
from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, StateGraph

from config import settings
from core.logging import get_logger
from core.pipeline.state import ChatState
from core.services import DBService, LLMService, VectorStoreService

logger = get_logger(__name__)


def build_chat_agent(
    llm: LLMService,
    vector: VectorStoreService,
    db: DBService,
):
    """Build and compile the chat agent graph.

    Invoke with:
        result = await agent.ainvoke({
            "user_input": "What's the duty on medical devices?",
            "context_doc_ids": [],  # optional — scope to specific docs
        })
    """
    top_k = settings.rag.top_k

    # ── Nodes ────────────────────────────────────────────────────────

    async def detect_language_node(state: ChatState) -> dict[str, Any]:
        lang = await llm.detect_language(state["user_input"])
        logger.info("Detected language: %s", lang)
        return {"detected_language": lang}

    async def detect_intent_node(state: ChatState) -> dict[str, Any]:
        intent = await llm.detect_intent(state["user_input"])
        logger.info("Detected intent: %s", intent)
        return {"intent": intent}

    async def retrieve_doc_qa_node(state: ChatState) -> dict[str, Any]:
        """Specific-document question: structured fields + semantic excerpts."""
        pg_docs = await _fetch_pg_documents(db, state)
        hits = await vector.search_docs(state["user_input"], top_k=top_k)
        logger.info("doc_qa: %d pg docs, %d chunks", len(pg_docs), len(hits))
        return {
            "pg_documents": pg_docs,
            "doc_chunks": [h.text for h in hits],
            "lex_chunks": [],
        }

    async def retrieve_rag_node(state: ChatState) -> dict[str, Any]:
        """Regulation question: customs-law chunks + adjacent siblings for full context."""
        hits = await vector.search_lex_with_context(state["user_input"], top_k=top_k)
        logger.info("rag: %d lex chunks (after sibling expansion)", len(hits))
        return {
            "pg_documents": [],
            "doc_chunks": [],
            "lex_chunks": [h.text for h in hits],
        }

    async def retrieve_hybrid_node(state: ChatState) -> dict[str, Any]:
        """Compliance question: pull from all three sources."""
        pg_docs = await _fetch_pg_documents(db, state)
        doc_hits = await vector.search_docs(state["user_input"], top_k=top_k)
        lex_hits = await vector.search_lex_with_context(state["user_input"], top_k=top_k)
        logger.info(
            "hybrid: %d pg docs, %d doc chunks, %d lex chunks (after sibling expansion)",
            len(pg_docs), len(doc_hits), len(lex_hits),
        )
        return {
            "pg_documents": pg_docs,
            "doc_chunks": [h.text for h in doc_hits],
            "lex_chunks": [h.text for h in lex_hits],
        }

    async def respond_node(state: ChatState) -> dict[str, Any]:
        context = _build_context(state)
        language = state.get("detected_language") or "en"
        response = await llm.chat(
            question=state["user_input"],
            context=context,
            language=language,
        )
        sources = _identify_sources(state)
        logger.info(
            "Response: %d chars, sources=%s",
            len(response), sources,
        )
        return {"final_response": response, "sources_used": sources}

    def route_by_intent(state: ChatState) -> str:
        # 'hybrid' is the safe default — uses all sources if intent is unclear.
        return state.get("intent") or "hybrid"

    # ── Assemble graph ───────────────────────────────────────────────

    graph = StateGraph(ChatState)
    graph.add_node("detect_language", detect_language_node)
    graph.add_node("detect_intent", detect_intent_node)
    graph.add_node("retrieve_doc_qa", retrieve_doc_qa_node)
    graph.add_node("retrieve_rag", retrieve_rag_node)
    graph.add_node("retrieve_hybrid", retrieve_hybrid_node)
    graph.add_node("respond", respond_node)

    graph.set_entry_point("detect_language")
    graph.add_edge("detect_language", "detect_intent")

    graph.add_conditional_edges(
        "detect_intent",
        route_by_intent,
        {
            "doc_qa": "retrieve_doc_qa",
            "rag": "retrieve_rag",
            "hybrid": "retrieve_hybrid",
        },
    )

    graph.add_edge("retrieve_doc_qa", "respond")
    graph.add_edge("retrieve_rag", "respond")
    graph.add_edge("retrieve_hybrid", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


# ── Helpers (module-level so they're easy to unit-test) ──────────────


async def _fetch_pg_documents(
    db: DBService, state: ChatState
) -> list[dict[str, Any]]:
    doc_ids = state.get("context_doc_ids") or []
    if doc_ids:
        return await db.get_documents(doc_ids)
    # No specific docs pinned — fall back to the 5 most recently processed docs
    # so doc_qa and hybrid still have structured context to work with.
    return await db.list_documents(limit=5)


def _build_context(state: ChatState) -> str:
    """Assemble retrieved sources into a single context string for the LLM."""
    parts: list[str] = []

    pg_docs = state.get("pg_documents") or []
    if pg_docs:
        parts.append("=== Structured document fields ===")
        for doc in pg_docs:
            header = f"Document {doc.get('id', '?')} ({doc.get('doc_type', '?')}):"
            body = json.dumps(
                doc.get("extracted_data") or {},
                indent=2,
                ensure_ascii=False,
            )
            parts.append(f"{header}\n{body}")

    doc_chunks = state.get("doc_chunks") or []
    if doc_chunks:
        parts.append("=== Relevant document excerpts ===")
        parts.extend(doc_chunks)

    lex_chunks = state.get("lex_chunks") or []
    if lex_chunks:
        parts.append("=== Uzbekistan customs-law references ===")
        parts.extend(lex_chunks)

    return "\n\n".join(parts) if parts else "(no context retrieved)"


def _identify_sources(state: ChatState) -> list[str]:
    sources: list[str] = []
    if state.get("pg_documents"):
        sources.append("postgresql")
    if state.get("doc_chunks"):
        sources.append("doc_chunks")
    if state.get("lex_chunks"):
        sources.append("lex_uz")
    return sources
