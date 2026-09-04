import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class SupplyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    quantity_available: Decimal = Field(ge=0)
    min_alert_qty: Decimal | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class SupplyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    quantity_available: Decimal | None = Field(default=None, ge=0)
    min_alert_qty: Decimal | None = Field(default=None, ge=0)
    unit_cost: Decimal | None = Field(default=None, ge=0)


class SupplyResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    quantity_available: Decimal
    min_alert_qty: Decimal | None
    unit_cost: Decimal | None
    is_active: bool
    low_stock: bool

    model_config = {"from_attributes": True}
