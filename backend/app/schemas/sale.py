import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.calculator import FilamentUsageInput, SupplyUsageInput

PAYMENT_METHODS = ("efectivo", "transferencia", "debito", "credito", "por_cobrar", "cortesia")


class SaleCreateRequest(BaseModel):
    sale_date: date
    client_name: str = Field(min_length=1, max_length=160)
    buyer_name: str | None = Field(default=None, max_length=160)
    printer_id: uuid.UUID
    filaments: list[FilamentUsageInput] = Field(default_factory=list)
    print_hours: Decimal = Field(ge=0, default=0)
    postprocess_hours: Decimal = Field(ge=0, default=0)
    base_price: Decimal = Field(ge=0)
    shipping_cost: Decimal = Field(ge=0, default=0)
    supplies: list[SupplyUsageInput] = Field(default_factory=list)
    payment_method: str = Field(pattern="^(" + "|".join(PAYMENT_METHODS) + ")$")
    notes: str | None = None


class SaleUpdateRequest(BaseModel):
    sale_date: date | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=160)
    buyer_name: str | None = Field(default=None, max_length=160)
    printer_id: uuid.UUID | None = None
    filaments: list[FilamentUsageInput] | None = None
    print_hours: Decimal | None = Field(default=None, ge=0)
    postprocess_hours: Decimal | None = Field(default=None, ge=0)
    base_price: Decimal | None = Field(default=None, ge=0)
    shipping_cost: Decimal | None = Field(default=None, ge=0)
    supplies: list[SupplyUsageInput] | None = None
    payment_method: str | None = Field(default=None, pattern="^(" + "|".join(PAYMENT_METHODS) + ")$")
    notes: str | None = None


class SaleSupplyResponse(BaseModel):
    supply_id: uuid.UUID
    supply_name: str
    quantity_used: Decimal
    unit_cost_snapshot: Decimal

    model_config = {"from_attributes": True}


class SaleFilamentResponse(BaseModel):
    filament_id: uuid.UUID
    filament_label: str
    grams_used: Decimal
    material_cost_snapshot: Decimal

    model_config = {"from_attributes": True}


class SaleResponse(BaseModel):
    id: uuid.UUID
    sale_date: date
    client_name: str
    buyer_name: str | None
    printer_id: uuid.UUID
    printer_name: str
    filament_id: uuid.UUID | None
    filament_label: str | None
    grams_used: Decimal
    print_hours: Decimal
    postprocess_hours: Decimal
    base_price: Decimal
    iva_percent: Decimal
    iva_amount: Decimal
    total_price: Decimal
    material_cost: Decimal
    depreciation_cost: Decimal
    energy_cost: Decimal
    postprocess_cost: Decimal
    supplies_cost: Decimal
    shipping_cost: Decimal
    total_cost: Decimal
    profit: Decimal
    margin_percent: Decimal
    payment_method: str
    notes: str | None
    supplies_used: list[SaleSupplyResponse]
    filaments_used: list[SaleFilamentResponse]

    model_config = {"from_attributes": True}


class SalePage(BaseModel):
    items: list[SaleResponse]
    total: int
