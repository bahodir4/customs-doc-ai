"""GTD (customs declaration) extraction prompt."""
from __future__ import annotations

from typing import Final

from core.prompts._base import build_system_prompt, build_user_prompt

_SPECIALTY: Final[str] = (
    "Specialty: customs declarations (GTD / cargo declaration / MRN). "
    "Identify the declaration number (MANDATORY — MRN for EU exports, "
    "local reg number for UZ), exporter, consignee, declarant, customs "
    "office, country fields (ISO-2), total values, and itemised line "
    "entries with HS codes."
)

_SCHEMA_TEMPLATE: Final[str] = """{
  "declaration_number": "string — MANDATORY (MRN like '25PL445010004F1CB7')",
  "declaration_date":   "YYYY-MM-DD or null",
  "declaration_type":   "string or null (EX, IM, TR)",
  "exporter": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null (EORI)"
  },
  "consignee": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "declarant": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "country_of_dispatch":    "ISO-2 or null",
  "country_of_destination": "ISO-2 or null",
  "customs_office":         "string or null",
  "incoterms":              "string or null",
  "total_invoice_value":    "number or null",
  "currency":               "ISO-3 or null",
  "total_gross_weight_kg":  "number or null",
  "total_packages":         "integer or null",
  "items": [
    {
      "item_number":        "integer or null",
      "hs_code":            "string or null",
      "description":        "string or null",
      "country_of_origin":  "ISO-2 or null",
      "gross_weight_kg":    "number or null",
      "net_weight_kg":      "number or null",
      "quantity":           "number or null",
      "statistical_value":  "number or null"
    }
  ]
}"""

GTD_SYSTEM: Final[str] = build_system_prompt(_SPECIALTY)


def gtd_prompt(raw_text: str) -> str:
    return build_user_prompt(_SCHEMA_TEMPLATE, raw_text)
