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
    # Solo para el observador (watcher): de qué usuario asignado es el inventario con que
    # se hace la venta. Para cualquier otro rol la venta es siempre del propio usuario.
    owner_id: uuid.UUID | None = None
    printer_id: uuid.UUID
    filaments: list[FilamentUsageInput] = Field(default_factory=list)
    print_hours: Decimal = Field(ge=0, default=0)
    postprocess_hours: Decimal = Field(ge=0, default=0)
    # Precio que se le cobra al cliente: el de un escenario sugerido o uno puesto a mano.
    price: Decimal = Field(ge=0)
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
    # Si no viene, la venta conserva exactamente el precio con que se registró.
    price: Decimal | None = Field(default=None, ge=0)
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


class ExhaustedFilamentInfo(BaseModel):
    filament_id: uuid.UUID
    filament_label: str

    model_config = {"from_attributes": True}


class SaleResponse(BaseModel):
    id: uuid.UUID
    sale_date: date
    client_name: str
    buyer_name: str | None
    # Dueño del inventario usado y quién registró la venta (pueden ser distintos si la
    # hizo un observador): se muestran siempre, por transparencia.
    owner_id: uuid.UUID
    owner_username: str
    created_by_user_id: uuid.UUID | None
    created_by_username: str | None
    printer_id: uuid.UUID
    printer_name: str
    filament_id: uuid.UUID | None
    filament_label: str | None
    grams_used: Decimal
    print_hours: Decimal
    postprocess_hours: Decimal
    # Lo que se le cobró al cliente.
    price: Decimal
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
    exhausted_filaments: list[ExhaustedFilamentInfo] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class SalePage(BaseModel):
    items: list[SaleResponse]
    total: int
