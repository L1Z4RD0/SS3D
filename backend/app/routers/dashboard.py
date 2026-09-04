import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
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

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _dated_sales_query(db: Session, user: User, date_from: date | None, date_to: date | None):
    query = db.query(Sale).filter(Sale.user_id == user.id)
    if date_from is not None:
        query = query.filter(Sale.sale_date >= date_from)
    if date_to is not None:
        query = query.filter(Sale.sale_date <= date_to)
    return query


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
        func.coalesce(func.sum(Sale.iva_amount), 0),
        func.coalesce(func.sum(Sale.print_hours), 0),
        func.coalesce(func.sum(Sale.grams_used), 0),
        func.coalesce(func.sum(Sale.depreciation_cost), 0),
        func.coalesce(func.sum(Sale.energy_cost), 0),
    ).one()

    total_jobs, total_revenue, total_profit, total_cost, total_iva, total_hours, total_grams, total_depr, total_energy = row

    avg_margin = Decimal(0)
    if total_revenue and Decimal(total_revenue) > 0:
        avg_margin = (Decimal(total_profit) / Decimal(total_revenue) * Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    return DashboardSummary(
        total_jobs=total_jobs,
        total_revenue=total_revenue,
        total_profit=total_profit,
        total_cost=total_cost,
        avg_margin_percent=avg_margin,
        total_iva=total_iva,
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
