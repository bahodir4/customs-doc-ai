"""Reusable schema components shared across document types.

These models are intentionally permissive — every field is Optional so the
extractor never throws away an otherwise-good document just because OCR
missed one field.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

_CONFIG = ConfigDict(
    str_strip_whitespace=True,
    extra="ignore",
    populate_by_name=True,
)


class Party(BaseModel):
    """A commercial counterparty — seller, buyer, shipper, consignee, etc."""

    model_config = _CONFIG

    name: Optional[str] = Field(default=None, description="Legal entity name")
    address: Optional[str] = Field(default=None, description="Full address")
    country: Optional[str] = Field(
        default=None, description="ISO-2 country code", max_length=2
    )
    tax_id: Optional[str] = Field(
        default=None, description="VAT, EORI, INN, or equivalent"
    )


class LineItem(BaseModel):
    """A single goods line on an invoice."""

    model_config = _CONFIG

    item_code: Optional[str] = None
    description: Optional[str] = None
    hs_code: Optional[str] = Field(
        default=None, description="HS / TN VED code"
    )
    quantity: Optional[float] = None
    unit: Optional[str] = Field(
        default=None, description="Unit of measure (pcs, kg, etc.)"
    )
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class BankDetails(BaseModel):
    """Banking information for invoice payment."""

    model_config = _CONFIG

    bank_name: Optional[str] = None
    iban: Optional[str] = None
    swift: Optional[str] = None
    account: Optional[str] = None
