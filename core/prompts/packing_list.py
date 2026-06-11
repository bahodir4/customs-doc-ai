"""Packing list extraction prompt."""
from __future__ import annotations

from typing import Final

from core.prompts._base import build_system_prompt, build_user_prompt

_SPECIALTY: Final[str] = (
    "Specialty: packing lists. Identify the packing list number "
    "(MANDATORY), date, related invoice number if cross-referenced, "
    "seller, buyer, itemised package details with weights and "
    "dimensions, and totals (packages, weights, volume)."
)

_SCHEMA_TEMPLATE: Final[str] = """{
  "packing_list_number":     "string — MANDATORY",
  "packing_list_date":       "YYYY-MM-DD or null",
  "related_invoice_number":  "string or null",
  "seller": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "buyer": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "items": [
    {
      "package_number":       "string or null",
      "description":          "string or null",
      "quantity_per_package": "number or null",
      "package_count":        "integer or null",
      "net_weight_kg":        "number or null",
      "gross_weight_kg":      "number or null",
      "dimensions":           "string or null (LxWxH in cm)"
    }
  ],
  "total_packages":         "integer or null",
  "total_gross_weight_kg":  "number or null",
  "total_net_weight_kg":    "number or null",
  "total_volume_m3":        "number or null",
  "shipping_marks":         "string or null"
}"""

PACKING_LIST_SYSTEM: Final[str] = build_system_prompt(_SPECIALTY)


def packing_list_prompt(raw_text: str) -> str:
    return build_user_prompt(_SCHEMA_TEMPLATE, raw_text)
