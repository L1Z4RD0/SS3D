from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.sale import Sale
from app.models.sale_supply import SaleSupply
from app.models.user import User
from app.schemas.calculator import (
    CalculatorSettingsResponse,
    CalculatorSettingsUpdateRequest,
    CostBreakdown as CostBreakdownSchema,
    QuoteRequest,
    QuoteResponse,
    SaveQuoteAsSaleRequest,
    ScenarioItem,
)
from app.schemas.sale import SaleResponse
from app.services.audit import log_event
from app.services.calculator import calculate_margin_percent, calculate_scenarios
from app.services.inventory import consume_filament, consume_supply
from app.services.sale_builder import (
    build_cost_breakdown,
    resolve_filament,
    resolve_printer,
    resolve_supplies,
    to_sale_response,
)
from app.services.settings import get_or_create_settings

router = APIRouter(prefix="/api/calculator", tags=["calculator"])


@router.get("/settings", response_model=CalculatorSettingsResponse)
def get_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    settings = get_or_create_settings(db, current_user.id)
    db.commit()
    return settings


@router.put("/settings", response_model=CalculatorSettingsResponse)
def update_settings(
    payload: CalculatorSettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user.id)
    for field, value in payload.model_dump().items():
        setattr(settings, field, value)

    log_event(
        db,
        user_id=current_user.id,
        event_type="CALCULATOR_SETTINGS_UPDATED",
        entity_type="calculator_settings",
        entity_id=settings.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(settings)
    return settings


@router.post("/quote", response_model=QuoteResponse)
def compute_quote(
    payload: QuoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_settings(db, current_user.id)
    printer = resolve_printer(db, current_user, payload.printer_id)
    filament = resolve_filament(db, current_user, payload.filament_id)
    resolved_supplies = resolve_supplies(db, current_user, payload.supplies)

    breakdown = build_cost_breakdown(
        printer=printer,
        filament=filament,
        resolved_supplies=resolved_supplies,
        grams_used=payload.grams_used,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        shipping_cost=payload.shipping_cost,
        electricity_rate=settings.electricity_rate,
        labor_rate_per_hour=settings.labor_rate_per_hour,
    )
    scenarios = calculate_scenarios(breakdown.total_cost, settings.margin_scenarios, settings.iva_percent)
    db.commit()

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

    settings = get_or_create_settings(db, current_user.id)
    printer = resolve_printer(db, current_user, payload.printer_id)
    filament = resolve_filament(db, current_user, payload.filament_id)
    resolved_supplies = resolve_supplies(db, current_user, payload.supplies)

    breakdown = build_cost_breakdown(
        printer=printer,
        filament=filament,
        resolved_supplies=resolved_supplies,
        grams_used=payload.grams_used,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        shipping_cost=payload.shipping_cost,
        electricity_rate=settings.electricity_rate,
        labor_rate_per_hour=settings.labor_rate_per_hour,
    )

    scenarios = {
        s.margin_percent: s
        for s in calculate_scenarios(breakdown.total_cost, [payload.chosen_margin_percent], settings.iva_percent)
    }
    scenario = scenarios.get(payload.chosen_margin_percent)
    if scenario is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Escenario de margen inválido")

    if filament is not None:
        consume_filament(filament, payload.grams_used)
    printer.hours_used += payload.print_hours

    sale = Sale(
        user_id=current_user.id,
        sale_date=sale_date,
        client_name=payload.client_name,
        buyer_name=payload.buyer_name,
        printer_id=printer.id,
        filament_id=filament.id if filament else None,
        grams_used=payload.grams_used,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        base_price=scenario.base_price,
        iva_percent=settings.iva_percent,
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

    return to_sale_response(sale)
