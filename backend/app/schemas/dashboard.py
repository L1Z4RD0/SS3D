import uuid
from decimal import Decimal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    total_jobs: int
    total_revenue: Decimal
    total_profit: Decimal
    total_cost: Decimal
    avg_margin_percent: Decimal
    total_iva: Decimal
    total_print_hours: Decimal
    total_filament_used_g: Decimal
    total_depreciation: Decimal
    total_energy: Decimal


class PrinterBreakdownItem(BaseModel):
    printer_id: uuid.UUID
    printer_name: str
    jobs: int
    hours: Decimal
    filament_g: Decimal
    revenue: Decimal
    profit: Decimal
    margin_percent: Decimal


class PaymentMethodBreakdownItem(BaseModel):
    payment_method: str
    jobs: int
    revenue: Decimal
    profit: Decimal


class StockAlertItem(BaseModel):
    filament_id: uuid.UUID
    brand: str
    type: str
    color: str
    sku: str | None
    available_g: Decimal
    min_alert_g: Decimal
    stock_percent: Decimal
    status: str
