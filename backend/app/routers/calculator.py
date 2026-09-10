from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.constants import ELECTRICITY_RATE, IVA_PERCENT, LABOR_RATE_PER_HOUR, MARGIN_SCENARIO_PERCENTS
from app.database import get_db
from app.dependencies import get_current_user
from app.models.sale import Sale
from app.models.sale_supply import SaleSupply
from app.models.user import User
from app.schemas.calculator import (
    CostBreakdown as CostBreakdownSchema,
    QuoteRequest,
    QuoteResponse,
    SaveQuoteAsSaleRequest,
    ScenarioItem,
)
from app.schemas.sale import SaleResponse
from app.services.audit import log_event
from app.services.calculator import calculate_margin_percent, calculate_scenarios, get_scenario_by_margin
from app.services.inventory import consume_supply
from app.services.sale_builder import (
    apply_filaments_to_sale,
    build_cost_breakdown,
    resolve_filaments,
    resolve_printer,
    resolve_supplies,
    to_sale_response,
)

router = APIRouter(prefix="/api/calculator", tags=["calculator"])


@router.post("/quote", response_model=QuoteResponse)
def compute_quote(
    payload: QuoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    printer = resolve_printer(db, current_user, payload.printer_id)
    resolved_filaments = resolve_filaments(db, current_user, payload.filaments)
    resolved_supplies = resolve_supplies(db, current_user, payload.supplies)

    breakdown = build_cost_breakdown(
        printer=printer,
        resolved_filaments=resolved_filaments,
        resolved_supplies=resolved_supplies,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        shipping_cost=payload.shipping_cost,
        electricity_rate=ELECTRICITY_RATE,
        labor_rate_per_hour=LABOR_RATE_PER_HOUR,
    )
    scenarios = calculate_scenarios(breakdown.total_cost)

    return QuoteResponse(
        breakdown=CostBreakdownSchema(
            material_cost=breakdown.material_cost,
            depreciation_cost=breakdown.depreciation_cost,
            energy_cost=breakdown.energy_cost,
            postprocess_cost=breakdown.postprocess_cost,
            supplies_cost=breakdown.supplies_cost,
            shipping_cost=breakdown.shipping_cost,
            total_cost=breakdown.total_cost,
        ),
        scenarios=[
            ScenarioItem(
                margin_percent=s.margin_percent,
                label=s.label,
                base_price=s.base_price,
                iva_amount=s.iva_amount,
                total_price=s.total_price,
                profit=s.profit,
            )
            for s in scenarios
        ],
    )


@router.post("/quote/save-as-sale", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def save_quote_as_sale(
    payload: SaveQuoteAsSaleRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        sale_date = date_type.fromisoformat(payload.sale_date)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fecha inválida, use formato YYYY-MM-DD")

    if payload.chosen_margin_percent not in MARGIN_SCENARIO_PERCENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escenario de margen inválido")

    printer = resolve_printer(db, current_user, payload.printer_id)
    resolved_filaments = resolve_filaments(db, current_user, payload.filaments)
    resolved_supplies = resolve_supplies(db, current_user, payload.supplies)

    breakdown = build_cost_breakdown(
        printer=printer,
        resolved_filaments=resolved_filaments,
        resolved_supplies=resolved_supplies,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        shipping_cost=payload.shipping_cost,
        electricity_rate=ELECTRICITY_RATE,
        labor_rate_per_hour=LABOR_RATE_PER_HOUR,
    )

    scenario = get_scenario_by_margin(breakdown.total_cost, payload.chosen_margin_percent)

    printer.hours_used += payload.print_hours

    sale = Sale(
        user_id=current_user.id,
        sale_date=sale_date,
        client_name=payload.client_name,
        buyer_name=payload.buyer_name,
        printer_id=printer.id,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        base_price=scenario.base_price,
        iva_percent=IVA_PERCENT,
        iva_amount=scenario.iva_amount,
        total_price=scenario.total_price,
        material_cost=breakdown.material_cost,
        depreciation_cost=breakdown.depreciation_cost,
        energy_cost=breakdown.energy_cost,
        postprocess_cost=breakdown.postprocess_cost,
        supplies_cost=breakdown.supplies_cost,
        shipping_cost=breakdown.shipping_cost,
        total_cost=breakdown.total_cost,
        profit=scenario.profit,
        margin_percent=calculate_margin_percent(scenario.base_price, breakdown.total_cost),
        payment_method=payload.payment_method,
        notes=payload.notes,
    )
    db.add(sale)
    db.flush()

    exhausted_filaments = apply_filaments_to_sale(db, sale, resolved_filaments)

    for supply, qty in resolved_supplies:
        consume_supply(supply, qty)
        db.add(
            SaleSupply(
                sale_id=sale.id,
                supply_id=supply.id,
                quantity_used=qty,
                unit_cost_snapshot=supply.unit_cost or Decimal(0),
            )
        )

    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_CREATED",
        entity_type="sale",
        entity_id=sale.id,
        details={"source": "calculator", "client_name": sale.client_name, "total_price": str(sale.total_price)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(sale)

    return to_sale_response(sale, exhausted_filaments)
