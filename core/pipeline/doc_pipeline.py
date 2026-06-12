"""Document processing pipeline.

A LangGraph state machine: load → ocr → classify → extract → validate → store.

Services are injected via closure so the pipeline is testable in isolation
and decoupled from settings. Each node is async and returns a partial
state update; LangGraph merges those into the running state.

Error handling uses a guard pattern: any node that fails sets
`status="error"` plus an `error_message`. Subsequent nodes short-circuit
when they see `status == "error"`. The final `store` node always runs
and persists whatever state we have — so even failed runs leave a
queryable record for inspection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import END, StateGraph

from config import settings
from core.logging import get_logger
from core.pipeline.state import DocProcessingState
from core.prompts import (
    DOC_TYPES,
    get_classify_prompt,
    get_extraction_prompt,
    normalise_classify_response,
)
from core.schemas import validate_and_parse
from core.services import DBService, LLMService, OCRService, VectorStoreService

logger = get_logger(__name__)


def _build_chunker() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.rag.chunk_size,
        chunk_overlap=settings.rag.chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def _is_error(state: DocProcessingState) -> bool:
    return state.get("status") == "error"


def build_doc_pipeline(
    ocr: OCRService,
    llm: LLMService,
    vector: VectorStoreService,
    db: DBService,
):
    """Build and compile the document-processing graph.

    Returns a LangGraph `CompiledStateGraph`. Invoke with:
        result = await pipeline.ainvoke({"file_path": "..."})
    """
    chunker = _build_chunker()

    # ── Nodes ────────────────────────────────────────────────────────

    async def load_node(state: DocProcessingState) -> dict[str, Any]:
        path_str = state["file_path"]
        path = Path(path_str)
        if not path.exists():
            return {
                "status": "error",
                "error_message": f"File not found: {path_str}",
            }
        return {
            "file_name": path.name,
            "file_type": path.suffix.lstrip(".").lower(),
            "status": "processing",
        }

    async def ocr_node(state: DocProcessingState) -> dict[str, Any]:
        if _is_error(state):
            return {"status": "error"}  # no-op write — LangGraph requires ≥1 field
        try:
            result = await ocr.extract_text(state["file_path"])
            logger.info(
                "OCR done: pages=%d chars=%d ocr_used=%s",
                result.page_count, len(result.text), result.ocr_used,
            )
            return {
                "raw_text": result.text,
                "ocr_pages": result.page_count,
                "ocr_used": result.ocr_used,
            }
        except Exception as exc:
            logger.exception("OCR failed")
            return {"status": "error", "error_message": f"OCR failed: {exc}"}

    async def classify_node(state: DocProcessingState) -> dict[str, Any]:
        if _is_error(state):
            return {"status": "error"}
        try:
            sys_p, usr_p = get_classify_prompt(state["raw_text"])
            raw = await llm.complete(sys_p, usr_p)
            doc_type = normalise_classify_response(raw)
            logger.info("Classified as: %s (raw=%r)", doc_type, raw[:50])
            return {"doc_type": doc_type}
        except Exception as exc:
            logger.exception("Classification failed")
            return {"status": "error", "error_message": f"Classify failed: {exc}"}

    async def extract_node(state: DocProcessingState) -> dict[str, Any]:
        if _is_error(state):
            return {"status": "error"}
        doc_type = state.get("doc_type", "unknown")
        if doc_type not in DOC_TYPES:
            logger.info("Skipping extraction: no schema for %s", doc_type)
            return {"extracted_data": {}, "validation_errors": []}
        try:
            sys_p, usr_p = get_extraction_prompt(doc_type, state["raw_text"])
            data = await llm.complete_json(sys_p, usr_p)
            logger.info("Extracted %d top-level fields", len(data))
            return {"extracted_data": data}
        except Exception as exc:
            logger.exception("Extraction failed")
            return {"status": "error", "error_message": f"Extract failed: {exc}"}

    async def validate_node(state: DocProcessingState) -> dict[str, Any]:
        if _is_error(state):
            return {"status": "error"}
        doc_type = state.get("doc_type")
        data = state.get("extracted_data") or {}
        if doc_type not in DOC_TYPES:
            return {"validation_errors": []}
        errors, cleaned = validate_and_parse(doc_type, data)
        if errors:
            logger.warning("Validation: %d error(s)", len(errors))
        else:
            logger.info("Validation: OK")
        return {"extracted_data": cleaned, "validation_errors": errors}

    async def store_node(state: DocProcessingState) -> dict[str, Any]:
        """Always runs — persists state regardless of upstream errors."""
        is_error = _is_error(state)
        final_status: str = "error" if is_error else "done"
        raw_text = state.get("raw_text") or ""

        try:
            doc_id = await db.save_document(
                doc_type=state.get("doc_type") or "unknown",
                file_name=state.get("file_name") or "",
                file_path=state["file_path"],
                raw_text=raw_text,
                extracted_data=state.get("extracted_data") or {},
                validation_errors=state.get("validation_errors") or [],
                status=final_status,
            )
            logger.info("Persisted doc_id=%s status=%s", doc_id, final_status)
        except Exception as exc:
            logger.exception("DB save failed")
            return {
                "status": "error",
                "error_message": f"Store failed: {exc}",
            }

        # Only embed if we have text and the pipeline succeeded otherwise.
        if raw_text and not is_error:
            try:
                chunks = chunker.split_text(raw_text)
                if chunks:
                    await vector.ensure_collections()
                    await vector.upsert_doc_chunks(doc_id, chunks)
                    logger.info("Embedded %d chunks into doc_chunks", len(chunks))
            except Exception as exc:
                # Embedding failure doesn't fail the run — the doc is saved,
                # the user just loses semantic search for it.
                logger.exception("Vector embed failed (doc still persisted)")
                return {
                    "doc_id": doc_id,
                    "status": "done",
                    "error_message": f"Embed failed: {exc}",
                }

        return {"doc_id": doc_id, "status": final_status}

    # ── Assemble graph ───────────────────────────────────────────────

    graph = StateGraph(DocProcessingState)
    graph.add_node("load", load_node)
    graph.add_node("ocr", ocr_node)
    graph.add_node("classify", classify_node)
    graph.add_node("extract", extract_node)
    graph.add_node("validate", validate_node)
    graph.add_node("store", store_node)

    graph.set_entry_point("load")
    graph.add_edge("load", "ocr")
    graph.add_edge("ocr", "classify")
    graph.add_edge("classify", "extract")
    graph.add_edge("extract", "validate")
    graph.add_edge("validate", "store")
    graph.add_edge("store", END)

    return graph.compile()