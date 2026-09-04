import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class CalculatorSettingsResponse(BaseModel):
    electricity_rate: Decimal
    labor_rate_per_hour: Decimal
    iva_percent: Decimal
    margin_scenarios: list[int]
    default_packaging_cost: Decimal | None

    model_config = {"from_attributes": True}


class CalculatorSettingsUpdateRequest(BaseModel):
    electricity_rate: Decimal = Field(ge=0)
    labor_rate_per_hour: Decimal = Field(ge=0)
    iva_percent: Decimal = Field(ge=0, le=100)
    margin_scenarios: list[int] = Field(min_length=1)
    default_packaging_cost: Decimal | None = Field(default=None, ge=0)


class SupplyUsageInput(BaseModel):
    supply_id: uuid.UUID
    quantity: Decimal = Field(gt=0)


class QuoteRequest(BaseModel):
    printer_id: uuid.UUID
    filament_id: uuid.UUID | None = None
    grams_used: Decimal = Field(ge=0, default=0)
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
