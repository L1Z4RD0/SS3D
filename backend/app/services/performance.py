"""Rendimiento por cuenta (solo la cuenta Empresa): Diego, Sntg y Simple_Solutions3D por
separado y todas juntas.

Regla de atribución (acordada con los socios):
- Ingresos, ganancia y pedidos: del DUEÑO de la venta (el dueño de la impresora), igual que
  en la cuenta de cada uno. Hasta el 2026-11-05 eran de la cuenta que la registró, y la
  Empresa aparecía con los ingresos de ventas que solo gestionó.
- "Registradas" (managed): las ventas que cada cuenta registró en la app, propias o de otra
  cuenta (la Empresa registra las de los socios). Solo informa quién las ingresó; no son
  ingresos suyos.
- Ingresos y costos van sin el delivery, que se muestra aparte (ver services/pricing).
- Costos: de quien puso cada recurso (ver cost_allocation): la máquina (depreciación + luz)
  al dueño de la impresora, el material al dueño de cada filamento, los insumos al dueño de
  cada insumo. La cuenta que registra no carga con costos que no son suyos.
- Horas de impresión y filamento usado: del dueño de la impresora y de cada filamento.
- "Todas juntas" cuenta cada venta UNA sola vez (aunque mezcle recursos de varias cuentas).

Mismas reglas que el Dashboard: solo pedidos Entregados, por su fecha real de entrega.
"""
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from app.dependencies import readable_user_ids
from app.models.sale import STATUS_DELIVERED, Sale
from app.models.sale_filament import SaleFilament
from app.models.sale_plate import SalePlate, SalePlateFilament
from app.models.user import User
from app.services.calculator import money
from app.services.cost_allocation import allocate_sale_costs
from app.services.pricing import cost_without_delivery, piece_price


@dataclass
class Totals:
    jobs: int = 0
    revenue: Decimal = Decimal(0)
    cost: Decimal = Decimal(0)
    profit: Decimal = Decimal(0)

    def add(self, sale: Sale) -> None:
        self.jobs += 1
        # Sin el delivery: no es ingreso ni costo del negocio (ver services/pricing).
        self.revenue += piece_price(sale)
        self.cost += cost_without_delivery(sale)
        self.profit += sale.profit

    def as_dict(self) -> dict:
        margin = (self.profit / self.revenue * 100) if self.revenue > 0 else Decimal(0)
        return {"jobs": self.jobs, "revenue": money(self.revenue), "cost": money(self.cost),
                "profit": money(self.profit), "margin_percent": money(margin)}


@dataclass
class OwnCosts:
    machine: Decimal = Decimal(0)
    material: Decimal = Decimal(0)
    supplies: Decimal = Decimal(0)
    postprocess: Decimal = Decimal(0)
    print_hours: Decimal = Decimal(0)
    filament_g: Decimal = Decimal(0)
    # Pedidos (de cualquier cuenta) en que se usó algo de esta cuenta.
    sales_with_resources: int = 0

    def as_dict(self) -> dict:
        return {"machine": money(self.machine), "material": money(self.material), "supplies": money(self.supplies),
                "postprocess": money(self.postprocess),
                "total": money(self.machine + self.material + self.supplies + self.postprocess),
                "print_hours": money(self.print_hours), "filament_g": money(self.filament_g),
                "sales_with_resources": self.sales_with_resources}


@dataclass
class Month:
    owned: dict = field(default_factory=lambda: defaultdict(Totals))
    managed: dict = field(default_factory=lambda: defaultdict(Totals))
    own_costs: dict = field(default_factory=lambda: defaultdict(Decimal))
    combined: Totals = field(default_factory=Totals)


def _usage_by_owner(sale: Sale) -> tuple[dict, dict]:
    """Horas de impresión y gramos de filamento por dueño de la impresora / del filamento."""
    hours: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    grams: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
    hours[sale.printer.user_id] += sale.print_hours
    plate_grams = Decimal(0)
    for plate in sale.plates:
        hours[plate.printer.user_id] += plate.print_hours
        for pf in plate.filaments_used:
            grams[pf.filament.user_id] += pf.grams_used
            plate_grams += pf.grams_used
    if sale.filaments_used:
        for sf in sale.filaments_used:
            grams[sf.filament.user_id] += sf.grams_used
    elif sale.grams_used - plate_grams > 0:
        # Ventas antiguas sin líneas de filamento: el material era del dueño de la venta.
        grams[sale.user_id] += sale.grams_used - plate_grams
    return hours, grams


def _sale_owner(sale: Sale, users: dict) -> uuid.UUID:
    """Dueño de la venta: el dueño de la impresora. Las ventas que la Empresa registró a su
    nombre antes del 2026-11-05 con la impresora de un socio se cuentan del socio (la misma
    corrección que se aplica al editarlas). Las del Almacén quedan como están."""
    registrant = users.get(sale.created_by_user_id)
    printer_owner = sale.printer.user_id
    if (sale.warehouse_item_id is None and registrant is not None and registrant.is_company
            and sale.user_id != printer_owner and printer_owner in users):
        return printer_owner
    return sale.user_id


def account_performance(db: Session, company: User, date_from: date | None, date_to: date | None) -> dict:
    ids = readable_user_ids(db, company)
    users = {u.id: u for u in db.query(User).filter(User.id.in_(ids)).all()}
    # Primero los socios (por nombre) y al final la Empresa.
    ordered = sorted(users.values(), key=lambda u: (u.is_company, u.username.lower()))

    query = (
        db.query(Sale)
        .options(
            selectinload(Sale.printer),
            selectinload(Sale.owner),
            selectinload(Sale.filaments_used).selectinload(SaleFilament.filament),
            selectinload(Sale.supplies_used),
            selectinload(Sale.plates).selectinload(SalePlate.printer),
            selectinload(Sale.plates).selectinload(SalePlate.filaments_used).selectinload(SalePlateFilament.filament),
        )
        .filter(Sale.status == STATUS_DELIVERED, or_(Sale.user_id.in_(ids), Sale.created_by_user_id.in_(ids)))
    )
    if date_from is not None:
        query = query.filter(Sale.delivered_date >= date_from)
    if date_to is not None:
        query = query.filter(Sale.delivered_date <= date_to)
    sales = query.order_by(Sale.delivered_date).all()

    owned: dict[uuid.UUID, Totals] = defaultdict(Totals)
    managed: dict[uuid.UUID, Totals] = defaultdict(Totals)
    own: dict[uuid.UUID, OwnCosts] = defaultdict(OwnCosts)
    combined = Totals()
    combined_hours = combined_grams = shared_cost = Decimal(0)
    mixed_sales = 0
    months: dict[str, Month] = defaultdict(Month)

    for sale in sales:
        owner = _sale_owner(sale, users)
        owned[owner].add(sale)
        combined.add(sale)
        month = months[sale.delivered_date.strftime("%Y-%m")]
        month.owned[owner].add(sale)
        month.combined.add(sale)
        # Quién la registró en la app (sea suya o de otra cuenta).
        registrant = sale.created_by_user_id
        if registrant in users:
            managed[registrant].add(sale)
            month.managed[registrant].add(sale)

        allocation = allocate_sale_costs(sale)
        shared_cost += sale.shipping_cost
        owners_here = set()
        for oc in allocation.owners:
            if oc.user_id not in users:
                continue
            o = own[oc.user_id]
            o.machine += oc.machine
            o.material += oc.material
            o.supplies += oc.supplies
            o.postprocess += oc.postprocess
            month.own_costs[oc.user_id] += oc.total
            owners_here.add(oc.user_id)
        hours, grams = _usage_by_owner(sale)
        for uid, h in hours.items():
            if uid in users:
                own[uid].print_hours += h
            combined_hours += h
        for uid, g in grams.items():
            if uid in users:
                own[uid].filament_g += g
            combined_grams += g
        for uid in owners_here:
            own[uid].sales_with_resources += 1
        if owners_here - {owner}:
            mixed_sales += 1

    return {
        "date_from": date_from,
        "date_to": date_to,
        "accounts": [
            {
                "user_id": u.id,
                "username": u.username,
                "is_company": u.is_company,
                "sales": owned[u.id].as_dict(),
                "managed": managed[u.id].as_dict(),
                "own_costs": own[u.id].as_dict(),
            }
            for u in ordered
        ],
        "combined": {
            **combined.as_dict(),
            "print_hours": money(combined_hours),
            "filament_g": money(combined_grams),
            # Delivery (de quien lo llevó): no es de una cuenta. El postprocesado ya está en los
            # costos propios del dueño de la impresora.
            "shared_cost": money(shared_cost),
            # Ventas que usaron recursos de una cuenta distinta a la del dueño.
            "mixed_sales": mixed_sales,
        },
        "months": [
            {
                "month": key,
                "accounts": {
                    str(u.id): {**months[key].owned[u.id].as_dict(), "own_cost": money(months[key].own_costs[u.id]),
                                "managed_jobs": months[key].managed[u.id].jobs}
                    for u in ordered
                },
                "combined": months[key].combined.as_dict(),
            }
            for key in sorted(months)
        ],
    }
