import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.constants import GRAMS_MAX


class SupplyUsageInput(BaseModel):
    supply_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class FilamentUsageInput(BaseModel):
    filament_id: uuid.UUID
    grams_used: Decimal = Field(gt=0, le=GRAMS_MAX)


class QuoteRequest(BaseModel):
    printer_id: uuid.UUID
    filaments: list[FilamentUsageInput] = Field(default_factory=list)
    print_hours: Decimal = Field(ge=0, default=0)
    postprocess_hours: Decimal = Field(ge=0, default=0)
    supplies: list[SupplyUsageInput] = Field(default_factory=list)
    shipping_cost: Decimal = Field(ge=0, default=0)


class CostBreakdown(BaseModel):
    material_cost: Decimal
    depreciation_cost: Decimal
    energy_cost: Decimal
    postprocess_cost: Decimal
    supplies_cost: Decimal
    shipping_cost: Decimal
    total_cost: Decimal


class ScenarioItem(BaseModel):
    margin_percent: int
    label: str
    base_price: Decimal
    iva_amount: Decimal
    total_price: Decimal
    profit: Decimal


class QuoteResponse(BaseModel):
    breakdown: CostBreakdown
    scenarios: list[ScenarioItem]


class SaveQuoteAsSaleRequest(QuoteRequest):
    sale_date: str
    client_name: str = Field(min_length=1, max_length=160)
    buyer_name: str | None = Field(default=None, max_length=160)
    payment_method: str
    notes: str | None = None
    chosen_margin_percent: int
