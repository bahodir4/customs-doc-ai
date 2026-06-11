"""Packing list schema."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from core.schemas.common import Party


_CONFIG = ConfigDict(
    str_strip_whitespace=True,
    extra="ignore",
    populate_by_name=True,
)


class PackageItem(BaseModel):
    """A single package or group of packages on a packing list."""

    model_config = _CONFIG

    package_number: Optional[str] = None
    description: Optional[str] = None
    quantity_per_package: Optional[float] = None
    package_count: Optional[int] = None
    net_weight_kg: Optional[float] = None
    gross_weight_kg: Optional[float] = None
    dimensions: Optional[str] = Field(
        default=None, description="LxWxH in cm or similar"
    )


class PackingListSchema(BaseModel):
    """A packing list — itemised description of shipment contents.

    `packing_list_number` is mandatory.
    """

    model_config = _CONFIG

    packing_list_number: str = Field(description="Packing list number (mandatory)")
    packing_list_date: Optional[str] = Field(default=None, description="ISO date")
    related_invoice_number: Optional[str] = None

    seller: Party = Field(default_factory=Party)
    buyer: Party = Field(default_factory=Party)

    items: list[PackageItem] = Field(default_factory=list)

    total_packages: Optional[int] = None
    total_gross_weight_kg: Optional[float] = None
    total_net_weight_kg: Optional[float] = None
    total_volume_m3: Optional[float] = None

    shipping_marks: Optional[str] = None
