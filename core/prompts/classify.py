"""Document type classification prompt."""
from __future__ import annotations

from typing import Final

CLASSIFY_SYSTEM: Final[str] = """You are a customs document classifier.

Read the provided text and classify it into exactly ONE of these codes:
- invoice       : commercial invoice, proforma invoice, sales invoice
                  (keywords: INVOICE, СЧЁТ-ФАКТУРА, RECHNUNG, FACTURA)
- awb           : air waybill, master AWB, house AWB
                  (keywords: Air Waybill, MAWB, HAWB, IATA, Shipper's Account Number)
- gtd           : customs declaration, GTD, MRN, EU export/import declaration (SAD/EX-A)
                  (keywords: Gruzovaya, UNIA EUROPEJSKA, MRN, Declaration, EX A, IM)
- cmr           : international road transport consignment note
                  (keywords: CMR, Consignment Note, Convention on the Contract)
- packing_list  : packing list, shipping list, packaging specification
                  (keywords: Packing List, УПАКОВОЧНЫЙ ЛИСТ, Packliste)
- letter        : declaration letter, cover letter, bank guarantee, supporting letter
- unknown       : cannot determine

The document text may be in English, Russian, Polish, German, or Uzbek.
Respond with the single code (lowercase). No quotes, no explanation, no punctuation."""

_MAX_CLASSIFY_CHARS: Final[int] = 2000


def classify_prompt(raw_text: str) -> str:
    """Build the user prompt for classification.

    Only the first ~2000 chars are needed — the document type is usually
    obvious from headers and the first table.
    """
    truncated = raw_text[:_MAX_CLASSIFY_CHARS]
    return f"Classify this document:\n\n{truncated}"
