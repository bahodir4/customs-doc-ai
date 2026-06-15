"""Document processing pipeline.

A LangGraph state machine: load → ocr → classify → extract → store.

Services are injected via closure so the pipeline is testable in isolation
and decoupled from settings. Each node is async and returns a partial
state update; LangGraph merges those into the running state.

Extraction is schema-free: the LLM organises all document data into
structured JSON using whatever groupings fit the document. This works for
any document type without hardcoded field names or Pydantic schemas.

Multi-page documents (≥ MAP_REDUCE_MIN_PAGES) use a two-phase approach:
  Phase 1 — full-text call for header/summary fields.
  Phase 2 — one parallel call per page for line items (more reliable
             association of prices with items in complex multi-column layouts).
  Phase 3 — deduplicate and merge per-page items into the header result.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Final

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.graph import END, StateGraph

from config import settings
from core.logging import get_logger
from core.pipeline.state import DocProcessingState
from core.prompts import (
    get_classify_prompt,
    get_correction_prompt,
    get_extraction_prompt,
    get_ocr_quality_prompt,
    get_page_items_prompt,
    normalise_classify_response,
)
from core.services import DBService, LLMService, OCRService, VectorStoreService

logger = get_logger(__name__)

# ── Map-reduce constants ──────────────────────────────────────────────────────

# Apply map-reduce when the document has at least this many pages.
_MAP_REDUCE_MIN_PAGES: Final[int] = 3

# Page-boundary markers inserted by OCRService (e.g. "--- Page 2 ---" or
# "--- Page 3 [OCR] ---").
_PAGE_MARKER: re.Pattern[str] = re.compile(
    r'---\s*Page\s+\d+(?:\s+\[[^\]]*\])?\s*---'
)

# Keys the organiser might use for the goods/line-items list.
_ITEMS_KEYS: Final[tuple[str, ...]] = (
    "goods", "line_items", "items", "goods_items", "products",
)


def _split_pages(raw_text: str) -> list[str]:
    """Split OCR text on page-boundary markers into per-page strings."""
    parts = _PAGE_MARKER.split(raw_text)
    return [p.strip() for p in parts if p.strip()]


async def _extract_page_items(
    llm: LLMService, page_text: str
) -> list[dict[str, Any]]:
    """Extract line items from a single page. Returns [] on any failure."""
    try:
        sys_p, usr_p = get_page_items_prompt(page_text)
        result = await llm.complete_json(sys_p, usr_p)
        items = result.get("items") or []
        return [i for i in items if isinstance(i, dict)]
    except Exception as exc:
        logger.warning("Per-page item extraction failed: %s", exc)
        return []


async def _map_reduce_extract(
    llm: LLMService,
    full_text: str,
    pages: list[str],
) -> dict[str, Any]:
    """Two-phase extraction for long multi-page documents.

    Phase 1 — organise the full text (header fields, totals, parties, etc.).
    Phase 2 — extract line items from each page in parallel.
    Phase 3 — deduplicate by item identity and merge into the header result.
    """
    # Phase 1: full document organisation (gives us header + fallback items)
    sys_p, usr_p = get_extraction_prompt(full_text)
    organised: dict[str, Any] = await llm.complete_json(sys_p, usr_p)

    # Phase 2: per-page item extraction (all pages concurrently)
    page_results: list[list[dict]] = list(
        await asyncio.gather(*[_extract_page_items(llm, pg) for pg in pages])
    )

    # Phase 3: deduplicate and merge
    seen: set[str] = set()
    merged: list[dict] = []
    for page_items in page_results:
        for item in page_items:
            key = str(
                item.get("item_code")
                or item.get("article")
                or item.get("description")
                or ""
            ).strip()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            merged.append(item)

    if merged:
        # Replace whatever key the organiser used with the better per-page results
        placed = False
        for candidate in _ITEMS_KEYS:
            if candidate in organised:
                organised[candidate] = merged
                placed = True
                break
        if not placed:
            organised["goods"] = merged
        logger.info(
            "Map-reduce: %d pages → %d items merged",
            len(pages), len(merged),
        )
    else:
        logger.warning("Map-reduce: per-page extraction empty; keeping full-text items")

    return organised


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

    Returns a LangGraph CompiledStateGraph. Invoke with:
        result = await pipeline.ainvoke({"file_path": "..."})
    """
    chunker = _build_chunker()

    # ── Nodes ────────────────────────────────────────────────────────────────

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
            return {"status": "error"}
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

    async def correct_node(state: DocProcessingState) -> dict[str, Any]:
        """Use the LLM to fix OCR errors in raw_text and return corrected_text.

        Falls back to raw_text unchanged if the LLM call fails, so the rest
        of the pipeline is never blocked by a correction failure.
        """
        if _is_error(state):
            return {}
        raw = state.get("raw_text", "")
        try:
            sys_p, usr_p = get_correction_prompt(raw)
            corrected = await llm.complete(sys_p, usr_p)
            corrected = corrected.strip()
            if not corrected:
                corrected = raw
            logger.info(
                "OCR correction: raw=%d chars → corrected=%d chars",
                len(raw), len(corrected),
            )
            return {"corrected_text": corrected}
        except Exception as exc:
            logger.warning("OCR correction failed, using raw text: %s", exc)
            return {"corrected_text": raw}

    async def quality_node(state: DocProcessingState) -> dict[str, Any]:
        if _is_error(state):
            return {}

        def _parse(result: dict, label: str) -> dict:
            q = {
                "rating": result.get("rating", "UNKNOWN"),
                "confidence": float(result.get("confidence", 0.0)),
                "readable_pct": int(result.get("readable_pct", 0)),
                "issues": result.get("issues") or [],
            }
            logger.info(
                "OCR quality [%s]: %s (readable=%d%%)",
                label, q["rating"], q["readable_pct"],
            )
            return q

        raw_text = state.get("raw_text", "")
        corrected_text = state.get("corrected_text") or raw_text

        try:
            sys_p_raw, usr_p_raw = get_ocr_quality_prompt(raw_text)
            sys_p_cor, usr_p_cor = get_ocr_quality_prompt(corrected_text)
            raw_result, cor_result = await asyncio.gather(
                llm.complete_json(sys_p_raw, usr_p_raw),
                llm.complete_json(sys_p_cor, usr_p_cor),
            )
            quality = {
                "raw": _parse(raw_result, "raw"),
                "corrected": _parse(cor_result, "corrected"),
            }
        except Exception as exc:
            logger.warning("OCR quality check failed: %s", exc)
            quality = {
                "raw": {"rating": "UNKNOWN", "issues": [str(exc)]},
                "corrected": {"rating": "UNKNOWN", "issues": []},
            }

        return {"ocr_quality": quality}

    async def classify_node(state: DocProcessingState) -> dict[str, Any]:
        if _is_error(state):
            return {"status": "error"}
        try:
            text = state.get("corrected_text") or state["raw_text"]
            sys_p, usr_p = get_classify_prompt(text)
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
        try:
            text = state.get("corrected_text") or state["raw_text"]
            pages = _split_pages(text)

            if len(pages) >= _MAP_REDUCE_MIN_PAGES:
                logger.info(
                    "Map-reduce extraction: %d pages (doc_type=%s)",
                    len(pages), state.get("doc_type"),
                )
                data = await _map_reduce_extract(llm, text, pages)
            else:
                sys_p, usr_p = get_extraction_prompt(text)
                data = await llm.complete_json(sys_p, usr_p)

            logger.info("Extraction complete: %d top-level keys", len(data))
            return {"extracted_data": data, "validation_errors": []}
        except Exception as exc:
            logger.exception("Extraction failed")
            return {"status": "error", "error_message": f"Extract failed: {exc}"}

    async def store_node(state: DocProcessingState) -> dict[str, Any]:
        """Always runs — persists state regardless of upstream errors."""
        is_error = _is_error(state)
        final_status = "error" if is_error else "done"
        raw_text = state.get("raw_text") or ""

        try:
            # Merge OCR quality metadata into extracted_data so it persists
            # without needing a separate DB column.
            extracted = dict(state.get("extracted_data") or {})
            if state.get("ocr_quality"):
                extracted["_ocr_quality"] = state["ocr_quality"]

            doc_id = await db.save_document(
                doc_type=state.get("doc_type") or "unknown",
                file_name=state.get("file_name") or "",
                file_path=state["file_path"],
                raw_text=raw_text,
                extracted_data=extracted,
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

        if raw_text and not is_error:
            try:
                chunks = chunker.split_text(raw_text)
                if chunks:
                    await vector.ensure_collections()
                    await vector.upsert_doc_chunks(doc_id, chunks)
                    logger.info("Embedded %d chunks into doc_chunks", len(chunks))
            except Exception as exc:
                logger.exception("Vector embed failed (doc still persisted)")
                return {
                    "doc_id": doc_id,
                    "status": "done",
                    "error_message": f"Embed failed: {exc}",
                }

        return {"doc_id": doc_id, "status": final_status}

    # ── Assemble graph ────────────────────────────────────────────────────────

    graph = StateGraph(DocProcessingState)
    graph.add_node("load", load_node)
    graph.add_node("ocr", ocr_node)
    graph.add_node("correct", correct_node)
    graph.add_node("quality", quality_node)
    graph.add_node("classify", classify_node)
    graph.add_node("extract", extract_node)
    graph.add_node("store", store_node)

    graph.set_entry_point("load")
    graph.add_edge("load", "ocr")
    graph.add_edge("ocr", "correct")
    graph.add_edge("correct", "quality")
    graph.add_edge("quality", "classify")
    graph.add_edge("classify", "extract")
    graph.add_edge("extract", "store")
    graph.add_edge("store", END)

    return graph.compile()
