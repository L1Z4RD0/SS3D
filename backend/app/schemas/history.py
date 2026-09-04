from decimal import Decimal

from pydantic import BaseModel


class MonthlySummary(BaseModel):
    year: int
    month: int
    label: str
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
