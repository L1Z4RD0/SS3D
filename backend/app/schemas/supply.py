import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class SupplyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    quantity_available: Decimal = Field(ge=0)
    min_alert_qty: Decimal | None = Field(default=None, ge=0)
    purchase_quantity: Decimal | None = Field(default=None, gt=0)
    purchase_total_cost: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _purchase_fields_together(self):
        if (self.purchase_quantity is None) != (self.purchase_total_cost is None):
            raise ValueError(
                "Indica tanto la cantidad comprada como el costo total de la compra, o deja ambos vacíos."
            )
        return self


class SupplyUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, min_length=1, max_length=60)
    quantity_available: Decimal | None = Field(default=None, ge=0)
    min_alert_qty: Decimal | None = Field(default=None, ge=0)
    purchase_quantity: Decimal | None = Field(default=None, gt=0)
    purchase_total_cost: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _purchase_fields_together(self):
        if (self.purchase_quantity is None) != (self.purchase_total_cost is None):
            raise ValueError(
                "Indica tanto la cantidad comprada como el costo total de la compra, o deja ambos vacíos."
            )
        return self


class SupplyResponse(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    quantity_available: Decimal
    min_alert_qty: Decimal | None
    purchase_quantity: Decimal | None
    purchase_total_cost: Decimal | None
    unit_cost: Decimal | None
    is_active: bool
    low_stock: bool

    model_config = {"from_attributes": True}
