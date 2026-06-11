"""Unit tests for Pydantic schemas — no external services needed."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.schemas import (
    DOC_TYPES,
    AWBSchema,
    CMRSchema,
    GTDSchema,
    InvoiceSchema,
    PackingListSchema,
    get_schema,
    validate_and_parse,
)


class TestMandatoryFields:
    """Each schema has exactly one mandatory field; everything else is Optional."""

    def test_invoice_requires_invoice_number(self) -> None:
        with pytest.raises(ValidationError):
            InvoiceSchema()
        assert InvoiceSchema(invoice_number="X-001").invoice_number == "X-001"

    def test_awb_requires_awb_number(self) -> None:
        with pytest.raises(ValidationError):
            AWBSchema()
        assert AWBSchema(awb_number="488-40007166").awb_number == "488-40007166"

    def test_gtd_requires_declaration_number(self) -> None:
        with pytest.raises(ValidationError):
            GTDSchema()
        assert GTDSchema(declaration_number="25PL445010004F1CB7")

    def test_cmr_requires_cmr_number(self) -> None:
        with pytest.raises(ValidationError):
            CMRSchema()
        assert CMRSchema(cmr_number="CMR-001")

    def test_packing_list_requires_number(self) -> None:
        with pytest.raises(ValidationError):
            PackingListSchema()
        assert PackingListSchema(packing_list_number="PL-001")


class TestInvoiceParsing:
    """Realistic invoice payloads, including nested seller/buyer/line_items."""

    def test_full_invoice_roundtrip(self) -> None:
        payload = {
            "invoice_number": "HQPL00073841",
            "invoice_date": "2025-09-15",
            "seller": {
                "name": "Ascensia Diabetes Care AG",
                "address": "Peter Merian-Strasse 90, 4052 Basel",
                "country": "CH",
                "tax_id": "CHE-456.789.012",
            },
            "buyer": {
                "name": "FE Medical Online Services LLC",
                "country": "UZ",
            },
            "line_items": [
                {
                    "item_code": "84123456",
                    "description": "CONTOUR PLUS test strips",
                    "hs_code": "3822190090",
                    "quantity": 1000,
                    "unit": "pcs",
                    "unit_price": 0.42,
                    "amount": 420.0,
                }
            ],
            "total_amount": 212584.80,
            "currency": "EUR",
            "incoterms": "DAP Tashkent",
            "bank": {"iban": "CH9300762011623852957", "swift": "UBSWCHZH80A"},
        }
        invoice = InvoiceSchema(**payload)
        dumped = invoice.model_dump(mode="json")
        assert dumped["invoice_number"] == "HQPL00073841"
        assert dumped["seller"]["country"] == "CH"
        assert len(dumped["line_items"]) == 1
        assert dumped["line_items"][0]["hs_code"] == "3822190090"
        assert dumped["bank"]["swift"] == "UBSWCHZH80A"

    def test_minimal_invoice_fills_defaults(self) -> None:
        invoice = InvoiceSchema(invoice_number="X-1")
        dumped = invoice.model_dump(mode="json")
        assert dumped["invoice_date"] is None
        assert dumped["line_items"] == []
        assert dumped["seller"] == {"name": None, "address": None, "country": None, "tax_id": None}
        assert dumped["bank"] is None

    def test_extra_fields_are_ignored(self) -> None:
        invoice = InvoiceSchema(
            invoice_number="X-1",
            unknown_llm_field="this should be dropped",
        )
        assert "unknown_llm_field" not in invoice.model_dump()

    def test_country_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError, match="country"):
            InvoiceSchema(invoice_number="X-1", seller={"country": "Switzerland"})

    def test_currency_too_long_rejected(self) -> None:
        with pytest.raises(ValidationError, match="currency"):
            InvoiceSchema(invoice_number="X-1", currency="EURO")


class TestValidateAndParse:
    """Public registry helper used by the pipeline (Phase 4)."""

    def test_round_trip_valid_invoice(self) -> None:
        errors, cleaned = validate_and_parse(
            "invoice", {"invoice_number": "X-1", "currency": "EUR"}
        )
        assert errors == []
        assert cleaned["invoice_number"] == "X-1"
        assert cleaned["currency"] == "EUR"

    def test_invalid_invoice_returns_errors_and_original(self) -> None:
        bad = {"missing_invoice_number_field": True}
        errors, returned = validate_and_parse("invoice", bad)
        assert errors, "expected at least one validation error"
        assert returned is bad  # original data passed through on failure

    def test_unknown_doc_type_returns_error(self) -> None:
        errors, returned = validate_and_parse("not_a_real_type", {"x": 1})
        assert any("not_a_real_type" in e for e in errors)
        assert returned == {"x": 1}

    @pytest.mark.parametrize("doc_type", DOC_TYPES)
    def test_get_schema_known_types(self, doc_type: str) -> None:
        schema = get_schema(doc_type)
        assert schema is not None

    def test_get_schema_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="No schema"):
            get_schema("phantom")
