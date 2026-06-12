"""Run the full document-processing pipeline on a file.

End-to-end CLI that exercises the LangGraph doc pipeline. Unlike
`extract_sample.py` (which doesn't persist), this script saves the
extracted data to PostgreSQL and embeds chunks into Qdrant — exactly
what the Streamlit upload page (Phase 6) will do.

Examples:
    python scripts/process_document.py "docs/sample_files/Final INVOICES .pdf"
    python scripts/process_document.py docs/sample_files/Avia.jpg --output result.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from core.logging import configure_logging, get_logger
from core.pipeline import build_doc_pipeline
from core.services import DBService, LLMService, OCRService, VectorStoreService

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process a customs document end-to-end through the pipeline.",
    )
    parser.add_argument("file", type=Path, help="Path to PDF, JPG, or PNG")
    parser.add_argument(
        "--output", "-o", type=Path, default=None,
        help="Write JSON result to this path (default: stdout)",
    )
    return parser.parse_args()


def _summarise(result: dict) -> dict:
    """Build a JSON-friendly summary of the pipeline result."""
    return {
        "doc_id":            result.get("doc_id"),
        "status":            result.get("status"),
        "doc_type":          result.get("doc_type"),
        "file_name":         result.get("file_name"),
        "ocr_pages":         result.get("ocr_pages"),
        "ocr_used":          result.get("ocr_used"),
        "raw_text_length":   len(result.get("raw_text") or ""),
        "validation_errors": result.get("validation_errors") or [],
        "extracted_data":    result.get("extracted_data") or {},
        "error_message":     result.get("error_message"),
    }


async def main() -> int:
    args = _parse_args()
    configure_logging(settings.log_level)

    if not args.file.exists():
        logger.error("File not found: %s", args.file)
        return 2

    # Wire services
    ocr = OCRService(language="en")
    llm = LLMService(settings.ollama)
    vector = VectorStoreService(settings.qdrant, settings.ollama)
    db = DBService(settings.postgres)

    try:
        pipeline = build_doc_pipeline(ocr, llm, vector, db)
        logger.info("Running doc pipeline on %s...", args.file)
        result = await pipeline.ainvoke({"file_path": str(args.file.resolve())})

        summary = _summarise(result)
        payload = json.dumps(summary, indent=2, ensure_ascii=False)

        if args.output:
            args.output.write_text(payload, encoding="utf-8")
            logger.info("Wrote result to %s", args.output)
        else:
            print(payload)

        return 0 if result.get("status") == "done" and not summary["validation_errors"] else 1
    finally:
        await vector.close()
        await db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
