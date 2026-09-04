import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class PrinterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purchase_value: Decimal = Field(gt=0)
    lifetime_hours: Decimal = Field(gt=0)
    power_kw: Decimal = Field(gt=0)


class PrinterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    purchase_value: Decimal | None = Field(default=None, gt=0)
    lifetime_hours: Decimal | None = Field(default=None, gt=0)
    power_kw: Decimal | None = Field(default=None, gt=0)
    hours_used: Decimal | None = Field(default=None, ge=0)


class PrinterResponse(BaseModel):
    id: uuid.UUID
    name: str
    purchase_value: Decimal
    lifetime_hours: Decimal
    power_kw: Decimal
    hours_used: Decimal
    depreciation_cost_per_hour: Decimal
    is_active: bool
    life_used_percent: Decimal
    life_remaining_hours: Decimal

    model_config = {"from_attributes": True}
