"""CMR (international road transport) extraction prompt."""
from __future__ import annotations

from typing import Final

from core.prompts._base import build_system_prompt, build_user_prompt

_SPECIALTY: Final[str] = (
    "Specialty: CMR consignment notes (international road transport). "
    "Identify the CMR number (MANDATORY), sender, consignee, carrier, "
    "places and date of taking-over and delivery, vehicle / trailer "
    "registration, and goods description with weight."
)

_SCHEMA_TEMPLATE: Final[str] = """{
  "cmr_number": "string — MANDATORY",
  "sender": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "consignee": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "carrier": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "place_of_taking_over": "string or null",
  "place_of_delivery":    "string or null",
  "date_of_taking_over":  "YYYY-MM-DD or null",
  "vehicle_registration": "string or null",
  "trailer_registration": "string or null",
  "goods_description":    "string or null",
  "gross_weight_kg":      "number or null",
  "volume_m3":            "number or null",
  "packages":             "integer or null",
  "instructions":         "string or null"
}"""

CMR_SYSTEM: Final[str] = build_system_prompt(_SPECIALTY)


def cmr_prompt(raw_text: str) -> str:
    return build_user_prompt(_SCHEMA_TEMPLATE, raw_text)
