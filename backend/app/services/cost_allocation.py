"""De quién es cada costo de una venta.

Cada recurso tiene dueño: la impresora (depreciación + luz) es de quien la compró, cada
filamento e insumo de quien lo compró. Una venta de la Empresa con la impresora de un socio
y filamento propio reparte así: la máquina al socio, el material a la Empresa. Se calcula
desde las líneas que ya guarda cada venta (no se guarda nada aparte), así que siempre
coincide con la venta aunque se edite.

El postprocesado y el envío no son de un recurso con dueño: quedan aparte (`shared`).
"""
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from app.models.sale import Sale
from app.services.calculator import money


@dataclass
class OwnerCosts:
    user_id: uuid.UUID
    username: str
    machine: Decimal = Decimal(0)  # depreciación + energía de sus impresoras
    material: Decimal = Decimal(0)  # filamento suyo usado
    supplies: Decimal = Decimal(0)  # insumos suyos usados

    @property
    def total(self) -> Decimal:
        return money(self.machine + self.material + self.supplies)


@dataclass
class SaleCostAllocation:
    owners: list[OwnerCosts] = field(default_factory=list)
    shared: Decimal = Decimal(0)  # postprocesado + envío


def allocate_sale_costs(sale: Sale) -> SaleCostAllocation:
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
        if oc.total != 0:
            owners.append(oc)
    owners.sort(key=lambda o: (o.user_id != sale.user_id, o.username.lower()))
    return SaleCostAllocation(owners=owners, shared=money(sale.postprocess_cost + sale.shipping_cost))
