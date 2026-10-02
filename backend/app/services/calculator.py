from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal

from app.constants import MARGIN_SCENARIOS, RISK_LEVELS

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
    # Costo sobre el que se aplica el margen (90/140/190): material + depreciación +
    # energía + insumos (el costo de producir la pieza).
    margin_base_cost: Decimal = Decimal(0)
    # Extras que se suman al final a precio de costo, sin margen: postprocesado y envío
    # (si el courier cobra $3.000, se cobran $3.000).
    extras_cost: Decimal = Decimal(0)
    supply_lines: list[SupplyUsage] = field(default_factory=list)
    filament_lines: list[FilamentUsage] = field(default_factory=list)
    # Riesgo de fallo: % de margin_base_cost que se cobra como reserva, fuera del margen.
    # No es un costo (no entra en total_cost): si la pieza no falla, queda como ganancia;
    # si falla, la reimpresión se registra como costo real.
    risk_percent: Decimal = Decimal(0)

    @property
    def risk_cost(self) -> Decimal:
        return money(self.margin_base_cost * self.risk_percent / Decimal(100))


@dataclass
class ScenarioResult:
    margin_percent: int
    label: str
    price: Decimal
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

    margin_base_cost = money(material_cost + depreciation_cost + energy_cost + supplies_cost)
    extras_cost = money(postprocess_cost + shipping)
    total_cost = money(margin_base_cost + extras_cost)

    return CostBreakdown(
        material_cost=material_cost,
        depreciation_cost=depreciation_cost,
        energy_cost=energy_cost,
        postprocess_cost=postprocess_cost,
        supplies_cost=supplies_cost,
        shipping_cost=shipping,
        total_cost=total_cost,
        margin_base_cost=margin_base_cost,
        extras_cost=extras_cost,
        supply_lines=supply_usages,
        filament_lines=filament_usages,
    )


def risk_level_for(percent: Decimal) -> str | None:
    """Nivel (bajo/medio/alto) que corresponde a un % guardado; None si no tenía riesgo."""
    for level, value in RISK_LEVELS.items():
        if Decimal(value) == percent:
            return level
    return None


def with_risk(breakdown: CostBreakdown, risk_level: str | None) -> CostBreakdown:
    """Aplica el riesgo de fallo elegido (bajo/medio/alto). Sin nivel, no hay riesgo."""
    percent = RISK_LEVELS.get(risk_level or "", 0)
    return replace(breakdown, risk_percent=Decimal(percent))


def _build_scenario(breakdown: CostBreakdown, margin_percent: int, label: str) -> ScenarioResult:
    # El margen se aplica sobre el costo de producción (material + depreciación + energía
    # + insumos); postprocesado, envío y el riesgo de fallo se suman después, sin margen.
    price = money(
        breakdown.margin_base_cost * (Decimal(1) + Decimal(margin_percent) / Decimal(100))
        + breakdown.extras_cost
        + breakdown.risk_cost
    )
    return ScenarioResult(
        margin_percent=margin_percent,
        label=label,
        price=price,
        profit=money(price - breakdown.total_cost),
    )


def calculate_scenarios(breakdown: CostBreakdown) -> list[ScenarioResult]:
    return [_build_scenario(breakdown, s["margin_percent"], s["label"]) for s in MARGIN_SCENARIOS]


def get_scenario_by_margin(breakdown: CostBreakdown, margin_percent: int) -> ScenarioResult | None:
    for s in MARGIN_SCENARIOS:
        if s["margin_percent"] == margin_percent:
            return _build_scenario(breakdown, margin_percent, s["label"])
    return None


def build_manual_price_scenario(total_cost: Decimal, price: Decimal) -> ScenarioResult:
    """El usuario fija el precio a su criterio (guiándose por los escenarios); la
    ganancia se calcula igual contra el costo total del trabajo."""
    price = money(price)
    return ScenarioResult(
        margin_percent=int(calculate_margin_percent(price, total_cost)),
        label="Precio manual",
        price=price,
        profit=money(price - total_cost),
    )


def calculate_margin_percent(price: Decimal, total_cost: Decimal) -> Decimal:
    if price <= 0:
        return Decimal(0)
    profit = price - total_cost
    return (profit / price * Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
