"""Shared prompt-construction helpers.

Every extraction prompt has the same general structure:
1. Role definition (customs analyst).
2. Specialty (what to look for in *this* document type).
3. Common output rules (JSON-only, null for missing, ISO codes, etc.).

This module centralises 1 and 3 so individual prompt modules only declare
their specialty + schema template.
"""
from __future__ import annotations

from typing import Final

MAX_TEXT_CHARS: Final[int] = 6000

_ROLE: Final[str] = (
    "You are an expert customs document analyst specialising in Uzbekistan "
    "import/export documentation. You extract structured data from OCR'd "
    "documents that may be in English, Russian, or Uzbek."
)

_RULES: Final[str] = """Output rules:
1. Return ONLY a valid JSON object. No markdown code fences. No commentary. No preamble.
2. For any field you cannot find, use null. Never guess or invent values.
3. Preserve original spelling for proper nouns (company names, addresses).
4. Country codes: ISO-2 (e.g. "CH" for Switzerland, "UZ" for Uzbekistan, "PL" for Poland).
5. Currency codes: ISO-3 (e.g. "EUR", "USD", "UZS").
6. Dates: ISO format YYYY-MM-DD.
7. Numbers: plain numerics, decimal point as separator, no thousands separators.
8. Weights in kilograms, volumes in cubic metres."""


def build_system_prompt(specialty: str) -> str:
    """Assemble a full system prompt from a doc-type-specific specialty line."""
    return f"{_ROLE}\n\n{specialty}\n\n{_RULES}"


def build_user_prompt(schema_template: str, raw_text: str) -> str:
    """Assemble the user prompt with the target schema and the OCR text."""
    truncated = raw_text[:MAX_TEXT_CHARS]
    return (
        f"Extract data into this exact JSON schema:\n\n"
        f"{schema_template}\n\n"
        f"Document text:\n"
        f"---\n"
        f"{truncated}\n"
        f"---"
    )
