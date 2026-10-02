"""Módulo BETA de Reparto e Inversión.

Es una guía aproximada para repartir el mes entre los socios, no una verdad contable: solo
LEE ventas e inventario (no cambia nada del resto de la app). Lo único que escribe son los
gastos de la Empresa, que solo se usan aquí.

Reglas (acordadas con los socios):
- Solo cuentan los pedidos Entregados en el mes y ya cobrados (no "Por cobrar").
- Los regalos (pago "Cortesía") quedan FUERA del reparto: no entra dinero, así que su costo
  lo absorbe quien regaló (no se le devuelve ni se reparte entre los demás).
- A cada socio se le devuelve lo que puso: máquina (depreciación + luz) de sus impresoras,
  y el material e insumos que eran suyos.
- Lo que pone la Empresa (su filamento/insumos) no se devuelve: lo compró la Caja y ya está
  en los gastos de la Empresa del mes.
- El postprocesado es ganancia común (no se le devuelve a nadie).
- El delivery (lo que pagó el cliente por el envío) se le devuelve a quien lo llevó: no es
  ganancia de nadie. Si no tiene a nadie asignado, queda "sin asignar".
- Neto = cobrado − costos devueltos a los socios − deliveries − gastos de la Empresa. Se
  reparte en partes iguales entre los socios y la Caja.
"""
import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, is_company, is_watcher
from app.models.company_expense import CompanyExpense
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import STATUS_DELIVERED, Sale
from app.models.user import User
from app.services.audit import log_event
from app.services.calculator import money
from app.services.cost_allocation import allocate_sale_costs

router = APIRouter(prefix="/api/beta", tags=["beta"])

CASH_BOX = "Caja"
UNCOLLECTED = "por_cobrar"
GIFT = "cortesia"


# ---------------------------------------------------------------------------
# Socios y acceso
# ---------------------------------------------------------------------------


def partner_names() -> list[str]:
    return [n.strip() for n in settings.split_partners.split(",") if n.strip()]


def _partner_for_username(username: str) -> str | None:
    for name in partner_names():
        if name.lower() == username.lower():
            return name
    return None


def require_split_access(current_user: User = Depends(get_current_user)) -> User:
    """El Reparto lo ven los socios, la Empresa y el administrador."""
    if current_user.role.name == "admin" or is_company(current_user) or _partner_for_username(current_user.username):
        return current_user
    raise HTTPException(status.HTTP_403_FORBIDDEN, "El Reparto (beta) es solo para los socios y la Empresa.")


def _involved_user_ids(db: Session) -> list[uuid.UUID]:
    """Cuentas del emprendimiento: las de los socios con usuario y las de la Empresa."""
    names = {n.lower() for n in partner_names()}
    users = db.query(User).all()
    return [u.id for u in users if u.username.lower() in names or u.is_company]


def _month_range(month: str) -> tuple[date, date]:
    try:
        year, mon = (int(x) for x in month.split("-"))
        return date(year, mon, 1), date(year, mon, monthrange(year, mon)[1])
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Mes inválido, usa el formato AAAA-MM.")


def _delivered_sales(db: Session, first: date, last: date) -> list[Sale]:
    ids = _involved_user_ids(db)
    return (
        db.query(Sale)
        .filter(
            Sale.status == STATUS_DELIVERED,
            Sale.delivered_date >= first,
            Sale.delivered_date <= last,
            or_(Sale.user_id.in_(ids), Sale.created_by_user_id.in_(ids)),
        )
        .order_by(Sale.delivered_date, Sale.created_at)
        .all()
    )


class BetaAccessResponse(BaseModel):
    split: bool
    investment: bool
    partners: list[str]


@router.get("/access", response_model=BetaAccessResponse)
def beta_access(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Qué vistas beta ve este usuario (para el menú)."""
    split = (
        current_user.role.name == "admin"
        or is_company(current_user)
        or _partner_for_username(current_user.username) is not None
    )
    owns_printer = db.query(Printer.id).filter(Printer.user_id == current_user.id).first() is not None
    return BetaAccessResponse(
        split=split, investment=not is_watcher(current_user) and owns_printer, partners=[*partner_names(), CASH_BOX]
    )


# ---------------------------------------------------------------------------
# Reparto del mes
# ---------------------------------------------------------------------------


class PartnerLine(BaseModel):
    name: str
    is_cash_box: bool = False
    cost_refund: Decimal = Decimal(0)  # lo que puso en máquina/material/insumos
    expense_refund: Decimal = Decimal(0)  # gastos de la Empresa que pagó de su bolsillo
    share: Decimal = Decimal(0)  # su parte del neto
    delivery_refund: Decimal = Decimal(0)  # deliveries que hizo (lo que pagó el cliente)
    total: Decimal = Decimal(0)  # share + todas las devoluciones


class SplitSaleLine(BaseModel):
    id: uuid.UUID
    delivered_date: date
    client_name: str
    owner_username: str
    created_by_username: str | None
    payment_method: str
    price: Decimal
    refunds: dict[str, Decimal]  # socio -> lo que se le devuelve por esta venta
    company_cost: Decimal  # costo puesto por la Empresa (no se devuelve)


class GiftLine(BaseModel):
    """Regalo del mes: fuera del reparto. Su costo lo absorbe cada dueño de lo que se usó."""

    id: uuid.UUID
    delivered_date: date
    client_name: str
    cost: Decimal
    absorbed_by: dict[str, Decimal]  # quién pone qué (no se le devuelve)


class PendingLine(BaseModel):
    id: uuid.UUID
    delivered_date: date
    client_name: str
    price: Decimal


class DeliveryLine(BaseModel):
    id: uuid.UUID
    delivered_date: date
    client_name: str
    delivery_by: str | None  # None = nadie asignado todavía
    amount: Decimal


class SplitResponse(BaseModel):
    month: str
    collected_revenue: Decimal
    partner_cost_refunds: Decimal
    company_absorbed_cost: Decimal
    expenses_total: Decimal
    deliveries_total: Decimal
    unassigned_delivery: Decimal
    net: Decimal
    parts: int
    partners: list[PartnerLine]
    sales: list[SplitSaleLine]
    pending: list[PendingLine]
    pending_total: Decimal
    gifts: list[GiftLine] = []
    gifts_cost: Decimal = Decimal(0)
    deliveries: list[DeliveryLine]


@router.get("/split", response_model=SplitResponse)
def monthly_split(
    month: str = Query(default_factory=lambda: date.today().strftime("%Y-%m")),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_split_access),
):
    first, last = _month_range(month)
    names = partner_names()
    lines = {n: PartnerLine(name=n) for n in names}
    lines[CASH_BOX] = PartnerLine(name=CASH_BOX, is_cash_box=True)

    collected = Decimal(0)
    company_cost = Decimal(0)
    sale_lines, pending, deliveries, gifts = [], [], [], []

    deliveries_total = Decimal(0)
    unassigned_delivery = Decimal(0)

    for sale in _delivered_sales(db, first, last):
        if sale.payment_method == GIFT:
            # Regalo: no entró dinero. Nada se devuelve ni se reparte; cada dueño absorbe lo suyo.
            absorbed = {}
            for oc in allocate_sale_costs(sale).owners:
                name = _partner_for_username(oc.username) or oc.username
                absorbed[name] = absorbed.get(name, Decimal(0)) + oc.total
            gifts.append(GiftLine(id=sale.id, delivered_date=sale.delivered_date, client_name=sale.client_name,
                                  cost=money(sale.total_cost), absorbed_by=absorbed))
            continue
        if sale.payment_method == UNCOLLECTED:
            pending.append(PendingLine(id=sale.id, delivered_date=sale.delivered_date, client_name=sale.client_name,
                                       price=sale.total_price))
            continue

        collected += sale.total_price
        # Delivery: lo cobrado por el envío es de quien lo llevó.
        if sale.shipping_cost > 0:
            deliveries_total += sale.shipping_cost
            deliveries.append(DeliveryLine(id=sale.id, delivered_date=sale.delivered_date, client_name=sale.client_name,
                                           delivery_by=sale.delivery_by, amount=sale.shipping_cost))
            if sale.delivery_by:
                who = next((n for n in lines if n.lower() == sale.delivery_by.lower()), None)
                if who is None:  # alguien que no está en la lista de socios
                    who = sale.delivery_by
                    lines[who] = PartnerLine(name=who)
                lines[who].delivery_refund += sale.shipping_cost
            else:
                unassigned_delivery += sale.shipping_cost
        refunds: dict[str, Decimal] = {}
        sale_company_cost = Decimal(0)
        for oc in allocate_sale_costs(sale).owners:
            owner_user = db.get(User, oc.user_id)
            if is_company(owner_user):
                sale_company_cost += oc.total
                continue
            name = _partner_for_username(oc.username) or oc.username
            if name not in lines:  # una cuenta que no está en la lista de socios
                lines[name] = PartnerLine(name=name)
            lines[name].cost_refund += oc.total
            refunds[name] = refunds.get(name, Decimal(0)) + oc.total
        company_cost += sale_company_cost
        sale_lines.append(SplitSaleLine(
            id=sale.id, delivered_date=sale.delivered_date, client_name=sale.client_name,
            owner_username=sale.owner.username,
            created_by_username=sale.created_by.username if sale.created_by else None,
            payment_method=sale.payment_method, price=sale.total_price, refunds=refunds,
            company_cost=money(sale_company_cost),
        ))

    expenses = _expenses_between(db, first, last)
    expenses_total = money(sum((e.amount for e in expenses), Decimal(0)))
    for e in expenses:
        who = next((n for n in lines if n.lower() == e.paid_by.lower()), None)
        if who and not lines[who].is_cash_box:
            lines[who].expense_refund += e.amount

    partner_refunds = money(sum((l.cost_refund for l in lines.values()), Decimal(0)))
    net = money(collected - partner_refunds - deliveries_total - expenses_total)
    parts = len(names) + 1  # socios + Caja
    share = money(net / parts) if parts else Decimal(0)
    for name in [*names, CASH_BOX]:
        lines[name].share = share
    for line in lines.values():
        line.cost_refund = money(line.cost_refund)
        line.expense_refund = money(line.expense_refund)
        line.delivery_refund = money(line.delivery_refund)
        line.total = money(line.share + line.cost_refund + line.expense_refund + line.delivery_refund)

    return SplitResponse(
        month=f"{first:%Y-%m}",
        collected_revenue=money(collected),
        partner_cost_refunds=partner_refunds,
        company_absorbed_cost=money(company_cost),
        expenses_total=expenses_total,
        deliveries_total=money(deliveries_total),
        unassigned_delivery=money(unassigned_delivery),
        net=net,
        parts=parts,
        partners=list(lines.values()),
        sales=sale_lines,
        pending=pending,
        pending_total=money(sum((p.price for p in pending), Decimal(0))),
        gifts=gifts,
        gifts_cost=money(sum((g.cost for g in gifts), Decimal(0))),
        deliveries=deliveries,
    )


# ---------------------------------------------------------------------------
# Gastos de la Empresa
# ---------------------------------------------------------------------------


class ExpenseRequest(BaseModel):
    expense_date: date
    concept: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(gt=0)
    paid_by: str = Field(min_length=1, max_length=60)


class ExpenseResponse(BaseModel):
    id: uuid.UUID
    expense_date: date
    concept: str
    amount: Decimal
    paid_by: str

    model_config = {"from_attributes": True}


def _expenses_between(db: Session, first: date, last: date) -> list[CompanyExpense]:
    return (
        db.query(CompanyExpense)
        .filter(CompanyExpense.expense_date >= first, CompanyExpense.expense_date <= last)
        .order_by(CompanyExpense.expense_date, CompanyExpense.created_at)
        .all()
    )


@router.get("/expenses", response_model=list[ExpenseResponse])
def list_expenses(
    month: str = Query(default_factory=lambda: date.today().strftime("%Y-%m")),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_split_access),
):
    first, last = _month_range(month)
    return _expenses_between(db, first, last)


@router.post("/expenses", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_split_access),
):
    expense = CompanyExpense(
        expense_date=payload.expense_date,
        concept=payload.concept.strip(),
        amount=money(payload.amount),
        paid_by=payload.paid_by.strip(),
        created_by_user_id=current_user.id,
    )
    db.add(expense)
    db.flush()
    log_event(db, user_id=current_user.id, event_type="COMPANY_EXPENSE_CREATED", entity_type="company_expense",
              entity_id=expense.id, details={"concept": expense.concept, "amount": str(expense.amount),
                                             "paid_by": expense.paid_by},
              ip_address=request.client.host if request.client else None)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_split_access),
):
    expense = db.get(CompanyExpense, expense_id)
    if expense is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gasto no encontrado")
    log_event(db, user_id=current_user.id, event_type="COMPANY_EXPENSE_DELETED", entity_type="company_expense",
              entity_id=expense.id, details={"concept": expense.concept, "amount": str(expense.amount)},
              ip_address=request.client.host if request.client else None)
    db.delete(expense)
    db.commit()


# ---------------------------------------------------------------------------
# Mi inversión
# ---------------------------------------------------------------------------


class InvestmentItem(BaseModel):
    name: str
    invested: Decimal
    recovered: Decimal


class InvestmentResponse(BaseModel):
    printers: list[InvestmentItem]
    filaments: InvestmentItem
    total_invested: Decimal
    total_recovered: Decimal


@router.get("/investment", response_model=InvestmentResponse)
def my_investment(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Cuánto lleva recuperado este socio de lo que invirtió: el valor de sus impresoras
    (con la depreciación + luz cobrada en cada venta) y lo que pagó por sus carretes (con el
    material suyo usado). Cuenta todos los pedidos Entregados y cobrados."""
    if is_watcher(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta vista es para los socios con impresoras propias.")
    printers = db.query(Printer).filter(Printer.user_id == current_user.id).order_by(Printer.name).all()
    printer_ids = {p.id for p in printers}
    machine_by_printer = {p.id: Decimal(0) for p in printers}
    my_filament_ids = {f.id for f in db.query(Filament.id).filter(Filament.user_id == current_user.id)}
    filaments_invested = money(
        sum((f.spool_price for f in db.query(Filament).filter(Filament.user_id == current_user.id)), Decimal(0))
    )
    material_recovered = Decimal(0)

    # Solo lo cobrado recupera inversión: ni lo "Por cobrar" ni los regalos (no entra dinero).
    sales = (
        db.query(Sale)
        .filter(Sale.status == STATUS_DELIVERED, Sale.payment_method.notin_([UNCOLLECTED, GIFT]))
        .all()
    )
    for sale in sales:
        plates_machine = Decimal(0)
        for plate in sale.plates:
            plates_machine += plate.depreciation_cost + plate.energy_cost
            if plate.printer_id in printer_ids:
                machine_by_printer[plate.printer_id] += plate.depreciation_cost + plate.energy_cost
            material_recovered += sum(
                (pf.material_cost_snapshot for pf in plate.filaments_used if pf.filament_id in my_filament_ids), Decimal(0)
            )
        if sale.printer_id in printer_ids:
            machine_by_printer[sale.printer_id] += sale.depreciation_cost + sale.energy_cost - plates_machine
        material_recovered += sum(
            (sf.material_cost_snapshot for sf in sale.filaments_used if sf.filament_id in my_filament_ids), Decimal(0)
        )

    printer_items = [
        InvestmentItem(name=p.name, invested=money(p.purchase_value), recovered=money(machine_by_printer[p.id]))
        for p in printers
    ]
    filament_item = InvestmentItem(name="Filamentos", invested=filaments_invested, recovered=money(material_recovered))
    return InvestmentResponse(
        printers=printer_items,
        filaments=filament_item,
        total_invested=money(sum((i.invested for i in printer_items), Decimal(0)) + filament_item.invested),
        total_recovered=money(sum((i.recovered for i in printer_items), Decimal(0)) + filament_item.recovered),
    )
