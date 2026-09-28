from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, is_watcher, readable_user_ids
from app.models.warehouse_item import ITEM_DISCARDED, ITEM_IN_STOCK, ITEM_RESERVED, WarehouseItem
from app.services.order_status import OPEN_STATUSES
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import Sale
from app.models.user import User
from app.schemas.dashboard import (
    DashboardSummary,
    PaymentMethodBreakdownItem,
    PrinterBreakdownItem,
    StockAlertItem,
)
from app.services.inventory import filament_stock_status
from app.models.sale import STATUS_CANCELLED, STATUS_DELIVERED
from app.services.sale_builder import sales_counted_for

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

LOCAL_TZ = "America/Santiago"


def _dated_sales_query(db: Session, user: User, date_from: date | None, date_to: date | None):
    # Solo cuentan los pedidos Entregados, por su fecha real de entrega: antes de eso el
    # dinero no entró. Dueño: los de su inventario (también los que registró un
    # observador). Observador: los que registró él.
    query = db.query(Sale).filter(sales_counted_for(user), Sale.status == STATUS_DELIVERED)
    if date_from is not None:
        query = query.filter(Sale.delivered_date >= date_from)
    if date_to is not None:
        query = query.filter(Sale.delivered_date <= date_to)
    return query


def _local_date(column):
    """Fecha en hora de Chile de una marca de tiempo (se guardan en UTC)."""
    return cast(func.timezone(LOCAL_TZ, column), Date)


def _orders_losses_and_warehouse(db: Session, user: User, date_from: date | None, date_to: date | None) -> dict:
    # Pedidos abiertos hoy (no dependen del período).
    open_orders = (
        db.query(func.count(Sale.id)).filter(sales_counted_for(user), Sale.status.in_(OPEN_STATUSES)).scalar() or 0
    )

    # Pérdidas del período. Una cancelación solo deja pérdida si la pieza no fue al
    # Almacén (loss_amount); las piezas descartadas cuentan su costo en la fecha del descarte.
    cancel_q = db.query(func.coalesce(func.sum(Sale.loss_amount), 0)).filter(
        sales_counted_for(user), Sale.status == STATUS_CANCELLED
    )
    discard_q = (
        db.query(func.coalesce(func.sum(WarehouseItem.cost), 0))
        .join(Sale, Sale.id == WarehouseItem.origin_sale_id)
        .filter(WarehouseItem.status == ITEM_DISCARDED)
    )
    if is_watcher(user):
        discard_q = discard_q.filter(Sale.created_by_user_id == user.id)
    else:
        discard_q = discard_q.filter(WarehouseItem.user_id == user.id)
    if date_from is not None:
        cancel_q = cancel_q.filter(_local_date(Sale.cancelled_at) >= date_from)
        discard_q = discard_q.filter(_local_date(WarehouseItem.discarded_at) >= date_from)
    if date_to is not None:
        cancel_q = cancel_q.filter(_local_date(Sale.cancelled_at) <= date_to)
        discard_q = discard_q.filter(_local_date(WarehouseItem.discarded_at) <= date_to)
    losses = Decimal(cancel_q.scalar() or 0) + Decimal(discard_q.scalar() or 0)

    # Valor en Almacén hoy: costo de piezas En almacén y Reservadas. El observador ve el
    # de sus usuarios asignados.
    value = (
        db.query(func.coalesce(func.sum(WarehouseItem.cost), 0))
        .filter(
            WarehouseItem.user_id.in_(readable_user_ids(db, user)),
            WarehouseItem.status.in_((ITEM_IN_STOCK, ITEM_RESERVED)),
        )
        .scalar()
    )
    return {"open_orders": open_orders, "total_losses": losses, "warehouse_value": value or 0}


@router.get("/summary", response_model=DashboardSummary)
def get_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
):
    query = _dated_sales_query(db, current_user, date_from, date_to)
    row = query.with_entities(
        func.count(Sale.id),
        func.coalesce(func.sum(Sale.base_price), 0),
        func.coalesce(func.sum(Sale.profit), 0),
        func.coalesce(func.sum(Sale.total_cost), 0),
        func.coalesce(func.sum(Sale.print_hours), 0),
        func.coalesce(func.sum(Sale.grams_used), 0),
        func.coalesce(func.sum(Sale.depreciation_cost), 0),
        func.coalesce(func.sum(Sale.energy_cost), 0),
    ).one()

    total_jobs, total_revenue, total_profit, total_cost, total_hours, total_grams, total_depr, total_energy = row

    avg_margin = Decimal(0)
    if total_revenue and Decimal(total_revenue) > 0:
        avg_margin = (Decimal(total_profit) / Decimal(total_revenue) * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    extra = _orders_losses_and_warehouse(db, current_user, date_from, date_to)

    return DashboardSummary(
        **extra,
        total_jobs=total_jobs,
        total_revenue=total_revenue,
        total_profit=total_profit,
        total_cost=total_cost,
        avg_margin_percent=avg_margin,
        total_print_hours=total_hours,
        total_filament_used_g=total_grams,
        total_depreciation=total_depr,
        total_energy=total_energy,
    )


@router.get("/by-printer", response_model=list[PrinterBreakdownItem])
def get_by_printer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
):
    query = _dated_sales_query(db, current_user, date_from, date_to)
    rows = (
        query.join(Printer, Sale.printer_id == Printer.id)
        .with_entities(
            Printer.id,
            Printer.name,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.print_hours), 0),
            func.coalesce(func.sum(Sale.grams_used), 0),
            func.coalesce(func.sum(Sale.base_price), 0),
            func.coalesce(func.sum(Sale.profit), 0),
        )
        .group_by(Printer.id, Printer.name)
        .order_by(func.coalesce(func.sum(Sale.base_price), 0).desc())
        .all()
    )

    items = []
    for printer_id, name, jobs, hours, grams, revenue, profit in rows:
        margin = Decimal(0)
        if revenue and Decimal(revenue) > 0:
            margin = (Decimal(profit) / Decimal(revenue) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        items.append(
            PrinterBreakdownItem(
                printer_id=printer_id,
                printer_name=name,
                jobs=jobs,
                hours=hours,
                filament_g=grams,
                revenue=revenue,
                profit=profit,
                margin_percent=margin,
            )
        )
    return items


@router.get("/by-payment-method", response_model=list[PaymentMethodBreakdownItem])
def get_by_payment_method(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
):
    query = _dated_sales_query(db, current_user, date_from, date_to)
    rows = (
        query.with_entities(
            Sale.payment_method,
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.base_price), 0),
            func.coalesce(func.sum(Sale.profit), 0),
        )
        .group_by(Sale.payment_method)
        .order_by(func.coalesce(func.sum(Sale.base_price), 0).desc())
        .all()
    )
    return [
        PaymentMethodBreakdownItem(payment_method=pm, jobs=jobs, revenue=revenue, profit=profit)
        for pm, jobs, revenue, profit in rows
    ]


@router.get("/stock-alerts", response_model=list[StockAlertItem])
def get_stock_alerts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    filaments = (
        db.query(Filament)
        .filter(Filament.user_id == current_user.id, Filament.is_active.is_(True))
        .order_by(Filament.brand, Filament.color)
        .all()
    )
    items = []
    for f in filaments:
        stock_percent, status = filament_stock_status(f)
        items.append(
            StockAlertItem(
                filament_id=f.id,
                brand=f.brand,
                type=f.type,
                color=f.color,
                sku=f.sku,
                available_g=f.available_g,
                min_alert_g=f.min_alert_g,
                stock_percent=stock_percent,
                status=status,
            )
        )
    return items
