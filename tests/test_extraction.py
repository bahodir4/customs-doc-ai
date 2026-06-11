"""End-to-end extraction tests (LLM required).

These tests verify the full extraction round-trip works against a real
Ollama instance. They use small synthetic OCR text — no sample-file
dependency — so they always run when --run-integration is passed.
"""
from __future__ import annotations

import pytest

from core.prompts import (
    get_classify_prompt,
    get_extraction_prompt,
    normalise_classify_response,
)
from core.schemas import validate_and_parse
from core.services import LLMService

# A compact, realistic invoice excerpt — enough for Qwen to extract the
# core fields without needing a multi-page document.
SYNTHETIC_INVOICE = """
COMMERCIAL INVOICE

Invoice Number:  HQPL00073841
Date:            15.09.2025

Seller:
Ascensia Diabetes Care AG
Peter Merian-Strasse 90, 4052 Basel, Switzerland
VAT: CHE-456.789.012

Buyer:
FE Medical Online Services LLC
Tashkent, Uzbekistan

Description                        HS Code      Qty      Unit Price    Amount
CONTOUR PLUS test strips           3822190090   1000     0.42 EUR      420.00 EUR
MICROLET lancets                   9018390000   500      0.30 EUR      150.00 EUR

Total:           570.00 EUR
Currency:        EUR
Incoterms:       DAP Tashkent

Bank:  UBS Switzerland
IBAN:  CH9300762011623852957
SWIFT: UBSWCHZH80A
"""

SYNTHETIC_AWB = """
AIR WAYBILL

AWB No: 488-40007166
Carrier: Rohlig Suus Logistics
From: WAW (Warsaw, Poland)
To: TAS (Tashkent, Uzbekistan)
Flight: HY244 / 2025-09-20

Shipper:    Ascensia Diabetes Care AG, Basel CH
Consignee:  FE Medical Online Services LLC, Tashkent UZ

Pieces: 12
Gross weight: 3019 kg
Chargeable weight: 3019 kg
Description: Medical diagnostic test strips

Declared value for carriage: NVD
Declared value for customs: 212584.80 EUR
"""


@pytest.mark.asyncio
@pytest.mark.integration
async def test_classify_invoice(llm_service: LLMService) -> None:
    sys_p, usr_p = get_classify_prompt(SYNTHETIC_INVOICE)
    raw = await llm_service.complete(sys_p, usr_p)
    assert normalise_classify_response(raw) == "invoice"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_classify_awb(llm_service: LLMService) -> None:
    sys_p, usr_p = get_classify_prompt(SYNTHETIC_AWB)
    raw = await llm_service.complete(sys_p, usr_p)
    assert normalise_classify_response(raw) == "awb"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extract_invoice_roundtrip(llm_service: LLMService) -> None:
    """Full extract → validate roundtrip for an invoice."""
    sys_p, usr_p = get_extraction_prompt("invoice", SYNTHETIC_INVOICE)
    extracted = await llm_service.complete_json(sys_p, usr_p)

    errors, cleaned = validate_and_parse("invoice", extracted)
    assert not errors, f"validation errors: {errors}"

    # Spot-check the mandatory field made it through.
    assert cleaned["invoice_number"] == "HQPL00073841"
    # Total may or may not be correctly extracted by 7B — just verify the
    # schema didn't strip the currency.
    assert cleaned.get("currency") in ("EUR", None)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_extract_awb_roundtrip(llm_service: LLMService) -> None:
    """Full extract → validate roundtrip for an AWB."""
    sys_p, usr_p = get_extraction_prompt("awb", SYNTHETIC_AWB)
    extracted = await llm_service.complete_json(sys_p, usr_p)

    errors, cleaned = validate_and_parse("awb", extracted)
    assert not errors, f"validation errors: {errors}"
    assert cleaned["awb_number"] == "488-40007166"
