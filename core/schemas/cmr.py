"""CMR (international road transport waybill) schema."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from core.schemas.common import Party


class CMRSchema(BaseModel):
    """A CMR consignment note — used for road transport across borders.

    `cmr_number` is mandatory.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="ignore",
        populate_by_name=True,
    )

    cmr_number: str = Field(description="CMR consignment note number (mandatory)")

    sender: Party = Field(default_factory=Party)
    consignee: Party = Field(default_factory=Party)
    carrier: Party = Field(default_factory=Party)

    place_of_taking_over: Optional[str] = None
    place_of_delivery: Optional[str] = None
    date_of_taking_over: Optional[str] = Field(default=None, description="ISO date")

    vehicle_registration: Optional[str] = None
    trailer_registration: Optional[str] = None

    goods_description: Optional[str] = None
    gross_weight_kg: Optional[float] = None
    volume_m3: Optional[float] = None
    packages: Optional[int] = None

    instructions: Optional[str] = Field(
        default=None, description="Sender instructions or special remarks"
    )
