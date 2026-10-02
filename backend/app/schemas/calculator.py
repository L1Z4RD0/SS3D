import uuid
from datetime import date
from decimal import Decimal

from typing import Literal

from pydantic import BaseModel, Field

from app.constants import GRAMS_MAX


class SupplyUsageInput(BaseModel):
    supply_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class FilamentUsageInput(BaseModel):
    filament_id: uuid.UUID
    grams_used: Decimal = Field(gt=0, le=GRAMS_MAX)


class PlateInput(BaseModel):
    """Plancha adicional: otra parte del mismo producto, con su impresora, horas y filamentos."""

    name: str = Field(min_length=1, max_length=80)
    printer_id: uuid.UUID
    print_hours: Decimal = Field(ge=0, default=0)
    filaments: list[FilamentUsageInput] = Field(default_factory=list)


class QuoteRequest(BaseModel):
    printer_id: uuid.UUID
    filaments: list[FilamentUsageInput] = Field(default_factory=list)
    print_hours: Decimal = Field(ge=0, default=0)
    postprocess_hours: Decimal = Field(ge=0, default=0)
    supplies: list[SupplyUsageInput] = Field(default_factory=list)
    shipping_cost: Decimal = Field(ge=0, default=0)
    # Planchas adicionales del mismo producto (la de arriba es la principal).
    extra_plates: list[PlateInput] = Field(default_factory=list, max_length=20)
    # Riesgo de fallo: bajo 10 %, medio 15 %, alto 20 % del costo de producción.
    risk_level: Literal["bajo", "medio", "alto"] = "bajo"


class CostBreakdown(BaseModel):
    material_cost: Decimal
    depreciation_cost: Decimal
    energy_cost: Decimal
    postprocess_cost: Decimal
    supplies_cost: Decimal
    shipping_cost: Decimal
    total_cost: Decimal
    # Material + depreciación + energía + insumos: sobre esto se aplica el margen.
    margin_base_cost: Decimal
    # Postprocesado + envío: se suman al final, sin margen.
    extras_cost: Decimal
    # Riesgo de fallo: se cobra fuera del margen y no es un costo (queda en la ganancia).
    risk_percent: Decimal = Decimal(0)
    risk_cost: Decimal = Decimal(0)


class ScenarioItem(BaseModel):
    margin_percent: int
    label: str
    price: Decimal
    profit: Decimal


class QuoteResponse(BaseModel):
    breakdown: CostBreakdown
    scenarios: list[ScenarioItem]


class SaveQuoteAsSaleRequest(QuoteRequest):
    sale_date: str
    # Fecha de entrega comprometida (si no viene, la del pedido).
    promised_delivery_date: date | None = None
    client_name: str = Field(min_length=1, max_length=160)
    buyer_name: str | None = Field(default=None, max_length=160)
    payment_method: str
    notes: str | None = None
    chosen_margin_percent: int
    # Precio fijado a mano por el usuario (ej. para redondear). Si viene, manda por
    # sobre chosen_margin_percent.
    manual_price: Decimal | None = Field(default=None, gt=0)
