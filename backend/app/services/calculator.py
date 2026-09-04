from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class SupplyUsage:
    supply_id: object
    quantity: Decimal
    unit_cost: Decimal


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


@dataclass
class ScenarioResult:
    margin_percent: int
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
    grams_used: Decimal,
    spool_weight_g: Decimal | None,
    spool_price: Decimal | None,
    print_hours: Decimal,
    depreciation_cost_per_hour: Decimal,
    power_kw: Decimal,
    electricity_rate: Decimal,
    postprocess_hours: Decimal,
    labor_rate_per_hour: Decimal,
    supply_usages: list[SupplyUsage],
    shipping_cost: Decimal,
) -> CostBreakdown:
    if spool_weight_g and spool_price and spool_weight_g > 0:
        material_cost = money((grams_used / spool_weight_g) * spool_price)
    else:
        material_cost = Decimal(0)

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
    )


def calculate_scenarios(
    total_cost: Decimal, margin_scenarios: list[int], iva_percent: Decimal
) -> list[ScenarioResult]:
    results = []
    for margin in margin_scenarios:
        base_price = money(total_cost * (Decimal(1) + Decimal(margin) / Decimal(100)))
        iva_amount = money(base_price * iva_percent / Decimal(100))
        total_price = money(base_price + iva_amount)
        profit = money(base_price - total_cost)
        results.append(
            ScenarioResult(
                margin_percent=margin,
                base_price=base_price,
                iva_amount=iva_amount,
                total_price=total_price,
                profit=profit,
            )
        )
    return results


def calculate_margin_percent(base_price: Decimal, total_cost: Decimal) -> Decimal:
    if base_price <= 0:
        return Decimal(0)
    profit = base_price - total_cost
    return (profit / base_price * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
