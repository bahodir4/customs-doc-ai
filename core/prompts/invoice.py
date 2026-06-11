"""Commercial invoice extraction prompt."""
from __future__ import annotations

from typing import Final

from core.prompts._base import build_system_prompt, build_user_prompt

_SPECIALTY: Final[str] = (
    "Specialty: commercial invoices. Identify the invoice number "
    "(MANDATORY), date, seller, buyer, line items (with HS codes if "
    "present), totals, currency, incoterms, and banking details."
)

_SCHEMA_TEMPLATE: Final[str] = """{
  "invoice_number":  "string — MANDATORY, do not return JSON without it",
  "invoice_date":    "YYYY-MM-DD or null",
  "seller": {
    "name":    "string or null",
    "address": "string or null",
    "country": "ISO-2 or null",
    "tax_id":  "string or null (VAT, EORI, INN)"
  },
  "buyer": {
    "name":    "string or null",
    "address": "string or null",
    "country": "ISO-2 or null",
    "tax_id":  "string or null"
  },
  "line_items": [
    {
      "item_code":   "string or null",
      "description": "string or null",
      "hs_code":     "string or null",
      "quantity":    "number or null",
      "unit":        "string or null (pcs, kg, l, etc.)",
      "unit_price":  "number or null",
      "amount":      "number or null"
    }
  ],
  "total_amount": "number or null",
  "currency":     "ISO-3 code or null (EUR, USD, UZS)",
  "incoterms":    "string or null (DAP Tashkent, FOB Hamburg, etc.)",
  "payment_terms": "string or null",
  "bank": {
    "bank_name": "string or null",
    "iban":      "string or null",
    "swift":     "string or null",
    "account":   "string or null"
  },
  "notes": "string or null"
}"""

INVOICE_SYSTEM: Final[str] = build_system_prompt(_SPECIALTY)


def invoice_prompt(raw_text: str) -> str:
    return build_user_prompt(_SCHEMA_TEMPLATE, raw_text)
