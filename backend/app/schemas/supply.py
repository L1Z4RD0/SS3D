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


class SupplyRestockRequest(BaseModel):
    # Lo que se compró y cuánto se pagó en total por esa compra.
    quantity: Decimal = Field(gt=0)
    total_cost: Decimal = Field(ge=0)


class SupplyResponse(BaseModel):
    id: uuid.UUID
    # Dueño del insumo: un watcher recibe los de varios usuarios y los separa por esto.
    owner_id: uuid.UUID
    name: str
    category: str
    quantity_available: Decimal
    min_alert_qty: Decimal | None
    purchase_quantity: Decimal | None
    purchase_total_cost: Decimal | None
    unit_cost: Decimal | None
    is_active: bool
    low_stock: bool
    # Unidades que se deben (stock en negativo): hay que comprarlas y registrarlas con Reponer.
    owed_qty: Decimal = Decimal(0)
    # Unidades ya usadas en ventas con costo provisional, esperando el precio real.
    pending_cost_qty: Decimal = Decimal(0)

    model_config = {"from_attributes": True}


class SupplyRestockResponse(BaseModel):
    supply: SupplyResponse
    # Unidades fiadas que esta compra saldó, en cuántas ventas y cuánto cambió su costo.
    settled_qty: Decimal
    repriced_sales: int
    cost_adjustment: Decimal
