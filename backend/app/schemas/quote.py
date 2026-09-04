import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class QuoteItemInput(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    quantity: Decimal = Field(gt=0, default=1)
    unit_price: Decimal = Field(ge=0)


class QuoteCreateRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=160)
    quote_date: date
    items: list[QuoteItemInput] = Field(min_length=1)


class QuoteItemResponse(BaseModel):
    id: uuid.UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal

    model_config = {"from_attributes": True}


class QuoteResponse(BaseModel):
    id: uuid.UUID
    quote_number: int
    client_name: str
    quote_date: date
    subtotal: Decimal
    iva_percent: Decimal
    iva_amount: Decimal
    total: Decimal
    created_at: datetime
    items: list[QuoteItemResponse]

    model_config = {"from_attributes": True}


class QuotePage(BaseModel):
    items: list[QuoteResponse]
    total: int
