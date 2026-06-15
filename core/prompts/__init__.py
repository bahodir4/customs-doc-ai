"""Prompt registry — single entry point for the orchestration layer.

Three public functions:
- `get_extraction_prompt(raw_text)`  → (system, user) universal doc organiser.
- `get_page_items_prompt(page_text)` → (system, user) single-page item extractor
                                        (used by the map-reduce path).
- `get_classify_prompt(raw_text)`    → (system, user) document type classifier.

The organiser is schema-free: the LLM decides what groupings fit the document.
This means any document type is supported without adding new prompt files.
"""
from __future__ import annotations

from typing import Final

from core.prompts.classify import CLASSIFY_SYSTEM, classify_prompt
from core.prompts.correct import CORRECTION_SYSTEM, correction_prompt
from core.prompts.organize import (
    ORGANIZE_SYSTEM,
    PAGE_ORGANIZE_SYSTEM,
    organize_prompt,
    page_organize_prompt,
)
from core.prompts.quality import _QUALITY_SYSTEM, ocr_quality_prompt

# Known classification labels — still used for UI filtering and routing.
DOC_TYPES: Final[tuple[str, ...]] = (
    "invoice",
    "awb",
    "gtd",
    "cmr",
    "packing_list",
)

CLASSIFY_LABELS: Final[tuple[str, ...]] = (*DOC_TYPES, "letter", "unknown")


def get_extraction_prompt(raw_text: str) -> tuple[str, str]:
    """Return (system, user) for universal document organisation."""
    return ORGANIZE_SYSTEM, organize_prompt(raw_text)


def get_page_items_prompt(page_text: str) -> tuple[str, str]:
    """Return (system, user) for single-page line-item extraction."""
    return PAGE_ORGANIZE_SYSTEM, page_organize_prompt(page_text)


def get_correction_prompt(raw_text: str) -> tuple[str, str]:
    """Return (system, user) for OCR text correction."""
    return CORRECTION_SYSTEM, correction_prompt(raw_text)


def get_classify_prompt(raw_text: str) -> tuple[str, str]:
    """Return (system, user) for document classification."""
    return CLASSIFY_SYSTEM, classify_prompt(raw_text)


def get_ocr_quality_prompt(raw_text: str) -> tuple[str, str]:
    """Return (system, user) for OCR quality assessment."""
    return _QUALITY_SYSTEM, ocr_quality_prompt(raw_text)


def normalise_classify_response(raw: str) -> str:
    """Map a raw LLM response to a known classification label."""
    token = raw.strip().lower().split()[0] if raw.strip() else ""
    token = token.strip(".,!?'\"")
    return token if token in CLASSIFY_LABELS else "unknown"


__all__ = [
    "CLASSIFY_LABELS",
    "DOC_TYPES",
    "get_classify_prompt",
    "get_correction_prompt",
    "get_extraction_prompt",
    "get_ocr_quality_prompt",
    "get_page_items_prompt",
    "normalise_classify_response",
]
