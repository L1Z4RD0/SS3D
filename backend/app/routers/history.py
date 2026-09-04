from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.sale import Sale
from app.models.user import User
from app.schemas.history import MonthlySummary

router = APIRouter(prefix="/api/history", tags=["history"])

MONTH_NAMES = [
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]


@router.get("/monthly", response_model=list[MonthlySummary])
def get_monthly_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    year_expr = extract("year", Sale.sale_date)
    month_expr = extract("month", Sale.sale_date)

    rows = (
        db.query(Sale)
        .filter(Sale.user_id == current_user.id)
        .with_entities(
            year_expr.label("year"),
            month_expr.label("month"),
            func.count(Sale.id),
            func.coalesce(func.sum(Sale.base_price), 0),
            func.coalesce(func.sum(Sale.profit), 0),
            func.coalesce(func.sum(Sale.total_cost), 0),
            func.coalesce(func.sum(Sale.iva_amount), 0),
            func.coalesce(func.sum(Sale.print_hours), 0),
            func.coalesce(func.sum(Sale.grams_used), 0),
            func.coalesce(func.sum(Sale.depreciation_cost), 0),
            func.coalesce(func.sum(Sale.energy_cost), 0),
        )
        .group_by(year_expr, month_expr)
        .order_by(year_expr.desc(), month_expr.desc())
        .all()
    )

    items = []
    for (
        year,
        month,
        total_jobs,
        total_revenue,
        total_profit,
        total_cost,
        total_iva,
        total_hours,
        total_grams,
        total_depr,
        total_energy,
    ) in rows:
        avg_margin = Decimal(0)
        if total_revenue and Decimal(total_revenue) > 0:
            avg_margin = (Decimal(total_profit) / Decimal(total_revenue) * Decimal(100)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        year_int = int(year)
        month_int = int(month)
        items.append(
            MonthlySummary(
                year=year_int,
                month=month_int,
                label=f"{MONTH_NAMES[month_int]} {year_int}",
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
        )
    return items
