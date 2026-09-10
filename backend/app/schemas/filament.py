import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.constants import GRAMS_MAX


class FilamentCreateRequest(BaseModel):
    brand: str = Field(min_length=1, max_length=120)
    type: str = Field(min_length=1, max_length=60)
    color: str = Field(min_length=1, max_length=60)
    sku: str | None = Field(default=None, max_length=60)
    entry_date: date
    spool_weight_g: Decimal = Field(default=Decimal(1000), gt=0, le=GRAMS_MAX)
    initial_stock_g: Decimal = Field(gt=0, le=GRAMS_MAX)
    min_alert_g: Decimal = Field(ge=0, le=GRAMS_MAX)
    spool_price: Decimal = Field(gt=0)


class FilamentUpdateRequest(BaseModel):
    brand: str | None = Field(default=None, min_length=1, max_length=120)
    type: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, min_length=1, max_length=60)
    sku: str | None = Field(default=None, max_length=60)
    entry_date: date | None = None
    spool_weight_g: Decimal | None = Field(default=None, gt=0, le=GRAMS_MAX)
    initial_stock_g: Decimal | None = Field(default=None, gt=0, le=GRAMS_MAX)
    min_alert_g: Decimal | None = Field(default=None, ge=0, le=GRAMS_MAX)
    spool_price: Decimal | None = Field(default=None, gt=0)


class FilamentResponse(BaseModel):
    id: uuid.UUID
    brand: str
    type: str
    color: str
    sku: str | None
    entry_date: date
    spool_weight_g: Decimal
    initial_stock_g: Decimal
    used_g: Decimal
    available_g: Decimal
    min_alert_g: Decimal
    spool_price: Decimal
    is_active: bool
    stock_percent: Decimal
    stock_status: str

    model_config = {"from_attributes": True}
