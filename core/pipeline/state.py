"""State definitions for both LangGraph pipelines.

LangGraph merges partial dicts returned from each node into the running
state, so `total=False` lets nodes return only the keys they actually
modify. The TypedDict serves as documentation of the full shape.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict


class DocProcessingState(TypedDict, total=False):
    """State for the document-processing pipeline.

    Flows through: load → ocr → classify → extract → validate → store.

    Only `file_path` is required at invocation; everything else is filled
    in by the nodes.
    """

    # ── Input ─────────────────────────────────────────────────────────
    file_path: str

    # ── Set by load_node ─────────────────────────────────────────────
    file_name: str
    file_type: str  # "pdf", "jpg", "png", etc.

    # ── Set by ocr_node ──────────────────────────────────────────────
    raw_text: str
    ocr_pages: int
    ocr_used: bool

    # ── Set by correct_node ──────────────────────────────────────────
    corrected_text: str  # LLM-cleaned version of raw_text; falls back to raw_text

    # ── Set by quality_node ──────────────────────────────────────────
    ocr_quality: dict[str, Any]  # {"rating": "GOOD"|"DEGRADED"|"UNREADABLE", ...}

    # ── Set by classify_node ─────────────────────────────────────────
    doc_type: str

    # ── Set by extract_node + validate_node ──────────────────────────
    extracted_data: dict[str, Any]
    validation_errors: list[str]

    # ── Set by store_node ────────────────────────────────────────────
    doc_id: str

    # ── Pipeline-wide ────────────────────────────────────────────────
    status: Literal["processing", "done", "error"]
    error_message: Optional[str]


class ChatState(TypedDict, total=False):
    """State for the chat agent graph.

    Flows through: detect_language → detect_intent → [retrieve_*] → respond.

    Routing after detect_intent is conditional on the `intent` value.
    """

    # ── Input ─────────────────────────────────────────────────────────
    user_input: str
    context_doc_ids: list[str]  # optional, scopes search to specific docs

    # ── Set by detect_language_node ──────────────────────────────────
    detected_language: Literal["uz", "ru", "en"]

    # ── Set by detect_intent_node ────────────────────────────────────
    intent: Literal["doc_qa", "rag", "hybrid"]

    # ── Set by retrieve_*_node (only the relevant ones for the intent) ─
    pg_documents: list[dict[str, Any]]
    doc_chunks: list[str]
    lex_chunks: list[str]

    # ── Set by retrieval pipeline (used by streaming path) ───────────
    context: str              # assembled context string ready to pass to LLM

    # ── Set by respond_node ──────────────────────────────────────────
    final_response: str
    sources_used: list[str]  # e.g. ["postgresql", "doc_chunks", "lex_uz"]
