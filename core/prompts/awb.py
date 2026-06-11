"""Air Waybill (AWB) extraction prompt."""
from __future__ import annotations

from typing import Final

from core.prompts._base import build_system_prompt, build_user_prompt

_SPECIALTY: Final[str] = (
    "Specialty: air waybills (AWB). Identify the AWB number "
    "(MANDATORY, format XXX-XXXXXXXX), shipper, consignee, carrier, "
    "airports of departure/destination (IATA codes), flight details, "
    "weight, pieces, and charges."
)

_SCHEMA_TEMPLATE: Final[str] = """{
  "awb_number":  "string — MANDATORY, format like '488-40007166'",
  "awb_type":    "string or null (MAWB or HAWB)",
  "shipper": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "consignee": {
    "name": "string or null", "address": "string or null",
    "country": "ISO-2 or null", "tax_id": "string or null"
  },
  "carrier":           "string or null (airline name)",
  "iata_carrier_code": "string or null (e.g. LH, BA, TK)",
  "airport_of_departure":   "IATA code or null (e.g. WAW, FRA)",
  "airport_of_destination": "IATA code or null (e.g. TAS)",
  "flight_number":      "string or null",
  "flight_date":        "YYYY-MM-DD or null",
  "pieces":              "integer or null",
  "gross_weight_kg":     "number or null",
  "chargeable_weight_kg":"number or null",
  "volume_m3":           "number or null",
  "description_of_goods":         "string or null",
  "declared_value_for_carriage":  "number or null",
  "declared_value_for_customs":   "number or null",
  "currency":          "ISO-3 or null",
  "freight_charges":   "number or null",
  "other_charges":     "number or null",
  "total_charges":     "number or null"
}"""

AWB_SYSTEM: Final[str] = build_system_prompt(_SPECIALTY)


def awb_prompt(raw_text: str) -> str:
    return build_user_prompt(_SCHEMA_TEMPLATE, raw_text)
