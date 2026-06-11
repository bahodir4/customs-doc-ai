"""GTD (customs declaration / cargo declaration) schema."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from core.schemas.common import Party


_CONFIG = ConfigDict(
    str_strip_whitespace=True,
    extra="ignore",
    populate_by_name=True,
)


class GTDLineItem(BaseModel):
    """A single declared item on a customs declaration."""

    model_config = _CONFIG

    item_number: Optional[int] = Field(default=None, description="Position number")
    hs_code: Optional[str] = Field(default=None, description="HS code / TN VED")
    description: Optional[str] = None
    country_of_origin: Optional[str] = Field(
        default=None, description="ISO-2 country code", max_length=2
    )
    gross_weight_kg: Optional[float] = None
    net_weight_kg: Optional[float] = None
    quantity: Optional[float] = None
    statistical_value: Optional[float] = None


class GTDSchema(BaseModel):
    """A customs cargo declaration (export, import, or transit).

    `declaration_number` is mandatory — often an MRN like
    `25PL445010004F1CB7` for EU exports.
    """

    model_config = _CONFIG

    declaration_number: str = Field(description="MRN or local registration number (mandatory)")
    declaration_date: Optional[str] = Field(default=None, description="ISO date")
    declaration_type: Optional[str] = Field(
        default=None, description="EX (export), IM (import), TR (transit), etc."
    )

    exporter: Party = Field(default_factory=Party)
    consignee: Party = Field(default_factory=Party)
    declarant: Optional[Party] = None

    country_of_dispatch: Optional[str] = Field(default=None, max_length=2)
    country_of_destination: Optional[str] = Field(default=None, max_length=2)

    customs_office: Optional[str] = None
    incoterms: Optional[str] = None

    total_invoice_value: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=3)
    total_gross_weight_kg: Optional[float] = None
    total_packages: Optional[int] = None

    items: list[GTDLineItem] = Field(default_factory=list)
