"""Extract structured data from a sample document.

End-to-end CLI that runs OCR → classify → extract → validate on a single
file and prints the result. Useful for testing extraction on real customs
documents before the pipeline (Phase 4) wires everything together.

Examples:
    python scripts/extract_sample.py tests/samples/invoice.pdf
    python scripts/extract_sample.py tests/samples/awb.jpg --type awb
    python scripts/extract_sample.py tests/samples/gtd.jpg --output extracted.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings
from core.logging import configure_logging, get_logger
from core.prompts import (
    DOC_TYPES,
    get_classify_prompt,
    get_extraction_prompt,
    normalise_classify_response,
)
from core.schemas import validate_and_parse
from core.services import LLMService, OCRService

logger = get_logger(__name__)


@dataclass
class ExtractionRun:
    """Full result of an extract_sample run."""

    file_path: str
    doc_type: str
    ocr_pages: int
    ocr_used: bool
    raw_text_length: int
    extracted: dict[str, Any]
    validation_errors: list[str]


async def run_extraction(
    file_path: Path,
    doc_type_override: Optional[str] = None,
) -> ExtractionRun:
    """OCR the file, classify (unless overridden), extract, validate."""
    ocr = OCRService(language="en")
    llm = LLMService(settings.ollama)

    logger.info("Step 1/4 — OCR: %s", file_path)
    ocr_result = await ocr.extract_text(file_path)
    logger.info(
        "  pages=%d chars=%d ocr_used=%s",
        ocr_result.page_count,
        len(ocr_result.text),
        ocr_result.ocr_used,
    )

    if doc_type_override:
        doc_type = doc_type_override
        logger.info("Step 2/4 — Classification skipped (--type=%s)", doc_type)
    else:
        logger.info("Step 2/4 — Classify...")
        sys_p, usr_p = get_classify_prompt(ocr_result.text)
        raw = await llm.complete(sys_p, usr_p)
        doc_type = normalise_classify_response(raw)
        logger.info("  raw=%r → doc_type=%s", raw[:60], doc_type)

    if doc_type not in DOC_TYPES:
        logger.warning("Classified as %r — no extraction schema; stopping.", doc_type)
        return ExtractionRun(
            file_path=str(file_path),
            doc_type=doc_type,
            ocr_pages=ocr_result.page_count,
            ocr_used=ocr_result.ocr_used,
            raw_text_length=len(ocr_result.text),
            extracted={},
            validation_errors=[f"No schema for doc_type {doc_type!r}"],
        )

    logger.info("Step 3/4 — Extract %s fields...", doc_type)
    sys_p, usr_p = get_extraction_prompt(doc_type, ocr_result.text)
    extracted_raw = await llm.complete_json(sys_p, usr_p)

    logger.info("Step 4/4 — Validate...")
    errors, cleaned = validate_and_parse(doc_type, extracted_raw)
    if errors:
        logger.warning("  validation errors: %d", len(errors))
        for err in errors:
            logger.warning("    - %s", err)
    else:
        logger.info("  validation: OK")

    return ExtractionRun(
        file_path=str(file_path),
        doc_type=doc_type,
        ocr_pages=ocr_result.page_count,
        ocr_used=ocr_result.ocr_used,
        raw_text_length=len(ocr_result.text),
        extracted=cleaned,
        validation_errors=errors,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OCR + classify + extract + validate a single document.",
    )
    parser.add_argument("file", type=Path, help="Path to PDF, JPG, or PNG file")
    parser.add_argument(
        "--type",
        dest="doc_type",
        choices=list(DOC_TYPES),
        default=None,
        help="Skip classification and use this doc type",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write JSON output to this path (default: stdout)",
    )
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    configure_logging(settings.log_level)

    if not args.file.exists():
        logger.error("File not found: %s", args.file)
        return 2

    result = await run_extraction(args.file, args.doc_type)
    payload = json.dumps(asdict(result), indent=2, ensure_ascii=False)

    if args.output:
        args.output.write_text(payload, encoding="utf-8")
        logger.info("Wrote result to %s", args.output)
    else:
        print(payload)

    return 0 if not result.validation_errors else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
