"""De quién es cada costo de una venta.

Cada recurso tiene dueño: la impresora (depreciación + luz) es de quien la compró, cada
filamento e insumo de quien lo compró. Una venta de la Empresa con la impresora de un socio
y filamento propio reparte así: la máquina al socio, el material a la Empresa. Se calcula
desde las líneas que ya guarda cada venta (no se guarda nada aparte), así que siempre
coincide con la venta aunque se edite.

El postprocesado lo hace el dueño de la impresora de la venta (la plancha principal), así
que es costo suyo. Hasta el 2026-11-02 quedaba aparte como "ganancia común" y no se le
devolvía a nadie. El delivery (shipping_cost) no es de un recurso: es de quien lo llevó
(Sale.delivery_by).
"""
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import object_session

from app.models.sale import Sale
from app.services.calculator import money


@dataclass
class OwnerCosts:
    user_id: uuid.UUID
    username: str
    machine: Decimal = Decimal(0)  # depreciación + energía de sus impresoras
    material: Decimal = Decimal(0)  # filamento suyo usado
    supplies: Decimal = Decimal(0)  # insumos suyos usados
    postprocess: Decimal = Decimal(0)  # postprocesado (lo hace el dueño de la impresora)

    @property
    def total(self) -> Decimal:
        return money(self.machine + self.material + self.supplies + self.postprocess)


@dataclass
class SaleCostAllocation:
    owners: list[OwnerCosts] = field(default_factory=list)


def allocate_sale_costs(sale: Sale) -> SaleCostAllocation:
    if sale.warehouse_item_id is not None:
        allocation = _allocate_warehouse_sale(sale)
        if allocation is not None:
            return allocation
    return _allocate_by_resources(sale)


def _allocate_by_resources(sale: Sale) -> SaleCostAllocation:
    by_owner: dict[uuid.UUID, OwnerCosts] = {}

    def owner(user) -> OwnerCosts:
        if user.id not in by_owner:
            by_owner[user.id] = OwnerCosts(user_id=user.id, username=user.username)
        return by_owner[user.id]

    # Máquina: la plancha principal es la impresora de la venta; cada plancha adicional, la suya.
    plates_machine = Decimal(0)
    for plate in sale.plates:
        plate_machine = plate.depreciation_cost + plate.energy_cost
        owner(plate.printer.owner).machine += plate_machine
        plates_machine += plate_machine
        for pf in plate.filaments_used:
            owner(pf.filament.owner).material += pf.material_cost_snapshot
    owner(sale.printer.owner).machine += sale.depreciation_cost + sale.energy_cost - plates_machine
    owner(sale.printer.owner).postprocess += sale.postprocess_cost

    # Material de la plancha principal, por dueño de cada filamento. Ventas antiguas sin
    # líneas de filamento: su material es del dueño de la venta.
    if sale.filaments_used:
        for sf in sale.filaments_used:
            owner(sf.filament.owner).material += sf.material_cost_snapshot
    else:
        plates_material = sum((pf.material_cost_snapshot for p in sale.plates for pf in p.filaments_used), Decimal(0))
        leftover = sale.material_cost - plates_material
        if leftover > 0:
            owner(sale.owner).material += leftover

    for ss in sale.supplies_used:
        owner(ss.supply.owner).supplies += ss.quantity_used * ss.unit_cost_snapshot + ss.cost_adjustment

    owners = []
    for oc in by_owner.values():
        oc.machine, oc.material, oc.supplies = money(oc.machine), money(oc.material), money(oc.supplies)
        oc.postprocess = money(oc.postprocess)
        if oc.total != 0:
            owners.append(oc)
    owners.sort(key=lambda o: (o.user_id != sale.user_id, o.username.lower()))
    return SaleCostAllocation(owners=owners)


# ---------------------------------------------------------------------------
# Lo que quedó consumido de un pedido cancelado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsumptionFactors:
    """Qué parte de cada costo del pedido se alcanzó a gastar."""

    material: Decimal  # 0 a 1: parte del filamento (y de su costo) que se usó
    machine: Decimal  # 0 a 1: parte de las horas de impresión (depreciación + luz) que se usó
    postprocess: bool  # si se hizo el postprocesado
    supplies: bool  # si los insumos quedaron consumidos


def planned_print_hours(sale: Sale) -> Decimal:
    """Horas de impresión del pedido completo: plancha principal + planchas adicionales."""
    return sale.print_hours + sum((p.print_hours for p in sale.plates), Decimal(0))


def consumption_factors(sale: Sale) -> ConsumptionFactors:
    """Desde la migración 0021, una cancelación con la pieza dañada guarda el % impreso, las
    horas usadas y si hubo postprocesado. Las anteriores (y las piezas que fueron al Almacén)
    siguen la regla de siempre: se consumió todo lo que no se devolvió al inventario."""
    if sale.cancel_printed_percent is not None:
        planned = planned_print_hours(sale)
        used = sale.cancel_print_hours or Decimal(0)
        return ConsumptionFactors(
            material=Decimal(sale.cancel_printed_percent) / 100,
            machine=min(Decimal(1), used / planned) if planned > 0 else Decimal(0),
            postprocess=bool(sale.cancel_postprocess_done),
            supplies=not sale.supplies_returned,
        )
    return ConsumptionFactors(
        material=Decimal(0) if sale.materials_returned else Decimal(1),
        machine=Decimal(0) if sale.hours_returned else Decimal(1),
        postprocess=True,
        supplies=not sale.supplies_returned,
    )


def allocate_consumed_costs(sale: Sale) -> SaleCostAllocation:
    """Costos de lo que quedó consumido tras cancelar, por dueño de cada recurso: la máquina
    y el postprocesado al dueño de la impresora, el material y los insumos a su dueño."""
    f = consumption_factors(sale)
    owners = []
    for oc in _allocate_by_resources(sale).owners:
        part = OwnerCosts(
            user_id=oc.user_id,
            username=oc.username,
            machine=money(oc.machine * f.machine),
            material=money(oc.material * f.material),
            supplies=oc.supplies if f.supplies else Decimal(0),
            postprocess=oc.postprocess if f.postprocess else Decimal(0),
        )
        if part.total != 0:
            owners.append(part)
    return SaleCostAllocation(owners=owners)


def consumed_total(sale: Sale) -> Decimal:
    return money(sum((oc.total for oc in allocate_consumed_costs(sale).owners), Decimal(0)))


def _allocate_warehouse_sale(sale: Sale) -> SaleCostAllocation | None:
    """Venta de una pieza del Almacén: su costo es lo que se consumió en el pedido original,
    así que se reparte igual que ese consumo (cada material a su dueño, insumos incluidos).
    Antes todo el material quedaba en el dueño de la pieza y los insumos no eran de nadie."""
    from app.models.warehouse_item import WarehouseItem  # evita importación circular

    db = object_session(sale)
    item = db.get(WarehouseItem, sale.warehouse_item_id) if db is not None else None
    origin = item.origin_sale if item is not None else None
    if origin is None:
        return None
    allocation = allocate_consumed_costs(origin)
    if not allocation.owners:
        return None
    # La pieza guarda su costo redondeado: cualquier centavo de diferencia va al material del
    # primer dueño, para que lo repartido sume exactamente el costo de la venta.
    diff = money(sale.total_cost - sum((oc.total for oc in allocation.owners), Decimal(0)))
    if diff:
        allocation.owners[0].material = money(allocation.owners[0].material + diff)
    return allocation
