"""Reponer un insumo: registrar la compra real y saldar lo que se usó "fiado".

Cuando se vende sin stock suficiente, el insumo queda en negativo y esas unidades se
costean provisionalmente al último precio conocido (SaleSupply.pending_qty). Al reponer
se sabe el precio real: la compra cubre primero lo fiado (de la venta más antigua a la
más nueva), recalcula esas unidades al precio real y corrige el costo, la ganancia y el
margen de cada venta afectada. Lo que sobra entra como stock normal.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.sale import STATUS_CANCELLED, Sale
from app.models.sale_supply import SaleSupply
from app.models.supply import Supply
from app.services.calculator import calculate_margin_percent, money


@dataclass
class RestockResult:
    settled_qty: Decimal = Decimal(0)
    # Cuánto cambió en total el costo de las ventas corregidas (+ si el insumo subió).
    cost_adjustment: Decimal = Decimal(0)
    sale_ids: list = field(default_factory=list)


def restock_supply(db: Session, supply: Supply, quantity: Decimal, total_cost: Decimal) -> RestockResult:
    unit_cost = money(total_cost / quantity)
    result = RestockResult()
    remaining = quantity

    lines = (
        db.query(SaleSupply)
        .join(Sale, Sale.id == SaleSupply.sale_id)
        .filter(SaleSupply.supply_id == supply.id, SaleSupply.pending_qty > 0)
        .order_by(Sale.created_at, SaleSupply.id)
        .all()
    )
    for line in lines:
        if remaining <= 0:
            break
        settle = min(line.pending_qty, remaining)
        # Lo saldado pasa del precio provisional al real; lo que siga pendiente queda
        # provisional al precio original de la línea.
        line.cost_adjustment = money(line.cost_adjustment + settle * (unit_cost - line.unit_cost_snapshot))
        line.pending_qty -= settle
        remaining -= settle
        result.settled_qty += settle
        result.cost_adjustment += _recompute_sale_supplies_cost(line.sale)
        if line.sale_id not in result.sale_ids:
            result.sale_ids.append(line.sale_id)

    supply.quantity_available += quantity
    # La última compra define el precio de los próximos usos.
    supply.purchase_quantity = quantity
    supply.purchase_total_cost = total_cost
    supply.unit_cost = unit_cost
    result.cost_adjustment = money(result.cost_adjustment)
    return result


def _recompute_sale_supplies_cost(sale: Sale) -> Decimal:
    """Recalcula el costo de insumos de la venta y lo propaga a su costo total, ganancia y
    margen. Devuelve la diferencia de costo."""
    new_supplies_cost = money(
        sum((ss.quantity_used * ss.unit_cost_snapshot + ss.cost_adjustment for ss in sale.supplies_used), Decimal(0))
    )
    delta = new_supplies_cost - sale.supplies_cost
    if delta == 0:
        return Decimal(0)
    sale.supplies_cost = new_supplies_cost
    sale.total_cost = money(sale.total_cost + delta)
    sale.profit = money(sale.profit - delta)
    sale.margin_percent = calculate_margin_percent(sale.base_price, sale.total_cost)
    # Cancelado con la pieza inutilizable: su pérdida incluía estos insumos.
    if sale.status == STATUS_CANCELLED and not sale.supplies_returned and sale.loss_amount > 0:
        sale.loss_amount = money(sale.loss_amount + delta)
    return delta
