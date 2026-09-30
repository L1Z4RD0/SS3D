from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.constants import ELECTRICITY_RATE, LABOR_RATE_PER_HOUR, MARGIN_SCENARIO_PERCENTS
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
from app.schemas.sale import GIFT_PAYMENT_METHOD, SaleResponse
from app.services.audit import log_event
from app.services.calculator import (
    build_manual_price_scenario,
    calculate_margin_percent,
    calculate_scenarios,
    get_scenario_by_margin,
)
from app.services.discord import announce_order
from app.services.inventory import consume_supply
from app.services.order_status import record_status, start_as_pending
from app.services.sale_builder import (
    apply_filaments_to_sale,
    build_cost_breakdown,
    resolve_filaments,
    resolve_printer,
    resolve_sale_owner,
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
    # Para cotizar, un observador puede combinar recursos de cualquiera de sus usuarios
    # asignados (solo para vender se exige que todo sea de un mismo dueño).
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

    return QuoteResponse(
        breakdown=CostBreakdownSchema(
            material_cost=breakdown.material_cost,
            depreciation_cost=breakdown.depreciation_cost,
            energy_cost=breakdown.energy_cost,
            postprocess_cost=breakdown.postprocess_cost,
            supplies_cost=breakdown.supplies_cost,
            shipping_cost=breakdown.shipping_cost,
            total_cost=breakdown.total_cost,
            margin_base_cost=breakdown.margin_base_cost,
            extras_cost=breakdown.extras_cost,
        ),
        scenarios=[
            ScenarioItem(margin_percent=s.margin_percent, label=s.label, price=s.price, profit=s.profit)
            for s in calculate_scenarios(breakdown)
        ],
    )


@router.post("/quote/save-as-sale", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def save_quote_as_sale(
    payload: SaveQuoteAsSaleRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        sale_date = date_type.fromisoformat(payload.sale_date)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Fecha inválida, use formato YYYY-MM-DD")

    manual_price = payload.manual_price
    if payload.payment_method == GIFT_PAYMENT_METHOD:
        manual_price = Decimal(0)  # regalo: sin cobro, los costos quedan igual
    if manual_price is None and payload.chosen_margin_percent not in MARGIN_SCENARIO_PERCENTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escenario de margen inválido")

    # La venta es del dueño de la impresora. Para vender, los filamentos e insumos tienen
    # que ser de ese mismo dueño (un observador puede cotizar mezclando, pero no vender así).
    printer = resolve_printer(db, current_user, payload.printer_id)
    owner_id = resolve_sale_owner(db, current_user, printer.user_id)
    resolved_filaments = resolve_filaments(db, current_user, payload.filaments)
    resolved_supplies = resolve_supplies(db, current_user, payload.supplies)
    foreign = [f for f, _ in resolved_filaments if f.user_id != owner_id] + [
        s for s, _ in resolved_supplies if s.user_id != owner_id
    ]
    if foreign:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Para guardar como venta, la impresora, los filamentos y los insumos deben ser del mismo usuario.",
        )

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

    if manual_price is not None:
        scenario = build_manual_price_scenario(breakdown.total_cost, manual_price)
    else:
        scenario = get_scenario_by_margin(breakdown, payload.chosen_margin_percent)

    printer.hours_used += payload.print_hours

    sale = Sale(
        user_id=owner_id,
        created_by_user_id=current_user.id,
        sale_date=sale_date,
        client_name=payload.client_name,
        buyer_name=payload.buyer_name,
        printer_id=printer.id,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        # Sin IVA: lo cobrado es el precio (columnas de IVA en 0, se conservan por las
        # ventas antiguas).
        base_price=scenario.price,
        iva_percent=0,
        iva_amount=0,
        total_price=scenario.price,
        material_cost=breakdown.material_cost,
        depreciation_cost=breakdown.depreciation_cost,
        energy_cost=breakdown.energy_cost,
        postprocess_cost=breakdown.postprocess_cost,
        supplies_cost=breakdown.supplies_cost,
        shipping_cost=breakdown.shipping_cost,
        total_cost=breakdown.total_cost,
        profit=scenario.profit,
        margin_percent=calculate_margin_percent(scenario.price, breakdown.total_cost),
        payment_method=payload.payment_method,
        notes=payload.notes,
    )
    start_as_pending(sale, payload.promised_delivery_date)
    db.add(sale)
    db.flush()
    record_status(db, sale, sale.status, current_user, "Pedido creado desde la Calculadora")

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
        details={
            "source": "calculator",
            "client_name": sale.client_name,
            "price": str(sale.total_price),
            "owner_id": str(owner_id),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(sale)

    response = to_sale_response(sale, exhausted_filaments, viewer=current_user)
    background_tasks.add_task(announce_order, sale.id)
    return response
