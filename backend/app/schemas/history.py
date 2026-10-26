from decimal import Decimal

from pydantic import BaseModel


class SourceTotals(BaseModel):
    jobs: int
    revenue: Decimal


class MonthlySummary(BaseModel):
    year: int
    month: int
    label: str
    total_jobs: int
    total_revenue: Decimal
    total_profit: Decimal
    total_cost: Decimal
    avg_margin_percent: Decimal
    total_print_hours: Decimal
    total_filament_used_g: Decimal
    total_depreciation: Decimal
    total_energy: Decimal
    # Pedidos e ingresos por fuente de venta ("instagram", "facebook", "personal" y
    # "sin_registrar" para los que no la tienen). Solo aparecen las fuentes con ventas.
    by_source: dict[str, SourceTotals] = {}
