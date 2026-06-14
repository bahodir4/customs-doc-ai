"""Commercial invoice schema."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from core.schemas.common import BankDetails, LineItem, Party


class InvoiceSchema(BaseModel):
    """A commercial invoice issued by a seller to a buyer.

    `invoice_number` is the only mandatory field — everything else can be
    null when OCR fails to find it. This keeps partial extraction useful.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="ignore",
        populate_by_name=True,
    )

    invoice_number: str = Field(description="Invoice number (mandatory)")
    invoice_date: Optional[str] = Field(
        default=None, description="Invoice date in ISO format YYYY-MM-DD"
    )
    original_or_copy: Optional[str] = Field(
        default=None, description="ORIGINAL or COPY"
    )
    contract_number: Optional[str] = Field(
        default=None, description="Contract or purchase-order reference"
    )

    seller: Party = Field(default_factory=Party)
    buyer: Party = Field(default_factory=Party)

    line_items: list[LineItem] = Field(default_factory=list)

    total_amount: Optional[float] = None
    currency: Optional[str] = Field(
        default=None, description="ISO-3 currency code (EUR, USD, UZS)", max_length=3
    )

    incoterms: Optional[str] = Field(
        default=None, description="Incoterms (DAP, FOB, CIF, etc.)"
    )
    payment_terms: Optional[str] = None

    bank: Optional[BankDetails] = None

    notes: Optional[str] = Field(
        default=None, description="Free-form notes or remarks"
    )
