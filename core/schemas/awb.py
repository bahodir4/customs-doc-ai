"""Air Waybill (AWB) schema."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from core.schemas.common import Party


class AWBSchema(BaseModel):
    """An air waybill — contract between shipper and air carrier.

    `awb_number` is mandatory (format typically "XXX-XXXXXXXX" where the
    first three digits are the airline prefix).
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="ignore",
        populate_by_name=True,
    )

    awb_number: str = Field(description="AWB number (mandatory)")
    awb_type: Optional[str] = Field(
        default=None, description="Master AWB (MAWB) or House AWB (HAWB)"
    )

    shipper: Party = Field(default_factory=Party)
    consignee: Party = Field(default_factory=Party)

    carrier: Optional[str] = Field(default=None, description="Airline / carrier name")
    iata_carrier_code: Optional[str] = Field(default=None, max_length=3)

    airport_of_departure: Optional[str] = Field(
        default=None, description="IATA airport code of origin"
    )
    airport_of_destination: Optional[str] = Field(
        default=None, description="IATA airport code of destination"
    )

    flight_number: Optional[str] = None
    flight_date: Optional[str] = Field(
        default=None, description="ISO date YYYY-MM-DD"
    )

    pieces: Optional[int] = Field(default=None, description="Number of packages")
    gross_weight_kg: Optional[float] = None
    chargeable_weight_kg: Optional[float] = None
    volume_m3: Optional[float] = None

    description_of_goods: Optional[str] = None
    declared_value_for_carriage: Optional[float] = None
    declared_value_for_customs: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=3)

    freight_charges: Optional[float] = None
    other_charges: Optional[float] = None
    total_charges: Optional[float] = None
