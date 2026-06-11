"""Prompt registry — single entry point for the orchestration layer.

Two public functions:
- `get_extraction_prompt(doc_type, raw_text)` → (system, user) for a
  doc-type-specific extraction call.
- `get_classify_prompt(raw_text)` → (system, user) for document
  classification.

Adding a new document type is a three-step process:
1. Define its Pydantic schema in `core.schemas`.
2. Create `core/prompts/<doc_type>.py` exporting `<DOC_TYPE>_SYSTEM` and
   a `<doc_type>_prompt(raw_text)` function.
3. Register both here.
"""
from __future__ import annotations

from typing import Callable, Final

from core.prompts.awb import AWB_SYSTEM, awb_prompt
from core.prompts.classify import CLASSIFY_SYSTEM, classify_prompt
from core.prompts.cmr import CMR_SYSTEM, cmr_prompt
from core.prompts.gtd import GTD_SYSTEM, gtd_prompt
from core.prompts.invoice import INVOICE_SYSTEM, invoice_prompt
from core.prompts.packing_list import PACKING_LIST_SYSTEM, packing_list_prompt

# Single source of truth for valid extraction targets.
DOC_TYPES: Final[tuple[str, ...]] = (
    "invoice",
    "awb",
    "gtd",
    "cmr",
    "packing_list",
)

# Classification can also produce these:
CLASSIFY_LABELS: Final[tuple[str, ...]] = (*DOC_TYPES, "letter", "unknown")

_PromptFn = Callable[[str], str]

_REGISTRY: Final[dict[str, tuple[str, _PromptFn]]] = {
    "invoice":      (INVOICE_SYSTEM,      invoice_prompt),
    "awb":          (AWB_SYSTEM,          awb_prompt),
    "gtd":          (GTD_SYSTEM,          gtd_prompt),
    "cmr":          (CMR_SYSTEM,          cmr_prompt),
    "packing_list": (PACKING_LIST_SYSTEM, packing_list_prompt),
}


def get_extraction_prompt(doc_type: str, raw_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for extracting `doc_type`."""
    if doc_type not in _REGISTRY:
        raise ValueError(
            f"No extraction prompt for doc_type {doc_type!r}. "
            f"Valid: {list(_REGISTRY)}"
        )
    system, user_fn = _REGISTRY[doc_type]
    return system, user_fn(raw_text)


def get_classify_prompt(raw_text: str) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for document classification."""
    return CLASSIFY_SYSTEM, classify_prompt(raw_text)


def normalise_classify_response(raw: str) -> str:
    """Map a raw LLM classification response to a known label.

    Returns 'unknown' if the response doesn't match any known label.
    """
    token = raw.strip().lower().split()[0] if raw.strip() else ""
    token = token.strip(".,!?'\"")
    return token if token in CLASSIFY_LABELS else "unknown"


__all__ = [
    "CLASSIFY_LABELS",
    "DOC_TYPES",
    "get_classify_prompt",
    "get_extraction_prompt",
    "normalise_classify_response",
]
