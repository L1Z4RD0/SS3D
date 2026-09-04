from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.constants import IVA_PERCENT, MARGIN_SCENARIOS

TWO_PLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class SupplyUsage:
    supply_id: object
    quantity: Decimal
    unit_cost: Decimal


@dataclass
class FilamentUsage:
    filament_id: object
    grams_used: Decimal
    spool_weight_g: Decimal
    spool_price: Decimal

    @property
    def material_cost(self) -> Decimal:
        if self.spool_weight_g and self.spool_weight_g > 0:
            return money((self.grams_used / self.spool_weight_g) * self.spool_price)
        return Decimal(0)


@dataclass
class CostBreakdown:
    material_cost: Decimal
    depreciation_cost: Decimal
    energy_cost: Decimal
    postprocess_cost: Decimal
    supplies_cost: Decimal
    shipping_cost: Decimal
    total_cost: Decimal
    supply_lines: list[SupplyUsage] = field(default_factory=list)
    filament_lines: list[FilamentUsage] = field(default_factory=list)


@dataclass
class ScenarioResult:
    margin_percent: int
    label: str
    base_price: Decimal
    iva_amount: Decimal
    total_price: Decimal
    profit: Decimal


def calculate_depreciation_cost_per_hour(purchase_value: Decimal, lifetime_hours: Decimal) -> Decimal:
    if lifetime_hours <= 0:
        return Decimal(0)
    return money(purchase_value / lifetime_hours)


def calculate_costs(
    *,
    filament_usages: list[FilamentUsage],
    print_hours: Decimal,
    depreciation_cost_per_hour: Decimal,
    power_kw: Decimal,
    electricity_rate: Decimal,
    postprocess_hours: Decimal,
    labor_rate_per_hour: Decimal,
    supply_usages: list[SupplyUsage],
    shipping_cost: Decimal,
) -> CostBreakdown:
    material_cost = money(sum((usage.material_cost for usage in filament_usages), Decimal(0)))
    depreciation_cost = money(print_hours * depreciation_cost_per_hour)
    energy_cost = money(print_hours * power_kw * electricity_rate)
    postprocess_cost = money(postprocess_hours * labor_rate_per_hour)
    supplies_cost = money(sum((usage.quantity * usage.unit_cost for usage in supply_usages), Decimal(0)))
    shipping = money(shipping_cost)

    total_cost = money(
        material_cost + depreciation_cost + energy_cost + postprocess_cost + supplies_cost + shipping
    )

    return CostBreakdown(
        material_cost=material_cost,
        depreciation_cost=depreciation_cost,
        energy_cost=energy_cost,
        postprocess_cost=postprocess_cost,
        supplies_cost=supplies_cost,
        shipping_cost=shipping,
        total_cost=total_cost,
        supply_lines=supply_usages,
        filament_lines=filament_usages,
    )


def _build_scenario(total_cost: Decimal, margin_percent: int, label: str) -> ScenarioResult:
    base_price = money(total_cost * (Decimal(1) + Decimal(margin_percent) / Decimal(100)))
    iva_amount = money(base_price * IVA_PERCENT / Decimal(100))
    total_price = money(base_price + iva_amount)
    profit = money(base_price - total_cost)
    return ScenarioResult(
        margin_percent=margin_percent,
        label=label,
        base_price=base_price,
        iva_amount=iva_amount,
        total_price=total_price,
        profit=profit,
    )


def calculate_scenarios(total_cost: Decimal) -> list[ScenarioResult]:
    return [_build_scenario(total_cost, s["margin_percent"], s["label"]) for s in MARGIN_SCENARIOS]


def get_scenario_by_margin(total_cost: Decimal, margin_percent: int) -> ScenarioResult | None:
    for s in MARGIN_SCENARIOS:
        if s["margin_percent"] == margin_percent:
            return _build_scenario(total_cost, margin_percent, s["label"])
    return None


def calculate_margin_percent(base_price: Decimal, total_cost: Decimal) -> Decimal:
    if base_price <= 0:
        return Decimal(0)
    profit = base_price - total_cost
    return (profit / base_price * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
