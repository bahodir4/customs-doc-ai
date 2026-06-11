"""Document type classification prompt."""
from __future__ import annotations

from typing import Final

CLASSIFY_SYSTEM: Final[str] = """You are a customs document classifier.

Read the provided text and classify it into exactly ONE of these codes:
- invoice       : commercial invoice, proforma invoice, sales invoice
- awb           : air waybill (master AWB or house AWB)
- gtd           : customs declaration, GTD, MRN export/import declaration
- cmr           : international road transport consignment note (CMR)
- packing_list  : packing list, shipping list, packaging specification
- letter        : declaration letter, cover letter, supporting letter
- unknown       : cannot determine

Respond with the single code (lowercase). No quotes, no explanation, no punctuation."""

_MAX_CLASSIFY_CHARS: Final[int] = 2000


def classify_prompt(raw_text: str) -> str:
    """Build the user prompt for classification.

    Only the first ~2000 chars are needed — the document type is usually
    obvious from headers and the first table.
    """
    truncated = raw_text[:_MAX_CLASSIFY_CHARS]
    return f"Classify this document:\n\n{truncated}"
