import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.sale import PAYMENT_METHODS


class WarehouseItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    owner_username: str
    origin_sale_id: uuid.UUID
    origin_client_name: str
    origin_cancelled_at: datetime | None
    entry_date: date
    cost: Decimal
    price: Decimal
    status: str
    discard_reason: str | None
    discarded_at: datetime | None
    notes: str | None
    # El dueño puede editar y descartar; el observador solo vender.
    can_manage: bool
    # Pedido que la tiene reservada o la vendió (si hay).
    active_sale_id: uuid.UUID | None


class WarehouseItemUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class WarehouseDiscardRequest(BaseModel):
    reason: str = Field(pattern="^(regalada|danada|desechada|otro)$")
    note: str | None = Field(default=None, max_length=500)


class WarehouseSellRequest(BaseModel):
    promised_delivery_date: date
    sale_date: date | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=160)
    buyer_name: str | None = Field(default=None, max_length=160)
    payment_method: str = Field(pattern="^(" + "|".join(PAYMENT_METHODS) + ")$")
    # Por defecto, el precio de venta de la pieza.
    price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None
