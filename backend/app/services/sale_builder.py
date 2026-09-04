import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import Sale
from app.models.supply import Supply
from app.models.user import User
from app.schemas.calculator import SupplyUsageInput
from app.schemas.sale import SaleResponse, SaleSupplyResponse
from app.services.calculator import CostBreakdown, SupplyUsage, calculate_costs


def resolve_printer(db: Session, user: User, printer_id: uuid.UUID) -> Printer:
    printer = db.query(Printer).filter(Printer.id == printer_id, Printer.user_id == user.id).first()
    if printer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Impresora no encontrada")
    return printer


def resolve_filament(db: Session, user: User, filament_id: uuid.UUID | None) -> Filament | None:
    if filament_id is None:
        return None
    filament = db.query(Filament).filter(Filament.id == filament_id, Filament.user_id == user.id).first()
    if filament is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filamento no encontrado")
    return filament


def resolve_supplies(
    db: Session, user: User, usages: list[SupplyUsageInput]
) -> list[tuple[Supply, Decimal]]:
    resolved: list[tuple[Supply, Decimal]] = []
    for usage in usages:
        supply = db.query(Supply).filter(Supply.id == usage.supply_id, Supply.user_id == user.id).first()
        if supply is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Insumo {usage.supply_id} no encontrado")
        resolved.append((supply, usage.quantity))
    return resolved


def build_cost_breakdown(
    *,
    printer: Printer,
    filament: Filament | None,
    resolved_supplies: list[tuple[Supply, Decimal]],
    grams_used: Decimal,
    print_hours: Decimal,
    postprocess_hours: Decimal,
    shipping_cost: Decimal,
    electricity_rate: Decimal,
    labor_rate_per_hour: Decimal,
) -> CostBreakdown:
    supply_usages = [
        SupplyUsage(supply_id=supply.id, quantity=qty, unit_cost=supply.unit_cost or Decimal(0))
        for supply, qty in resolved_supplies
    ]
    return calculate_costs(
        grams_used=grams_used,
        spool_weight_g=filament.spool_weight_g if filament else None,
        spool_price=filament.spool_price if filament else None,
        print_hours=print_hours,
        depreciation_cost_per_hour=printer.depreciation_cost_per_hour,
        power_kw=printer.power_kw,
        electricity_rate=electricity_rate,
        postprocess_hours=postprocess_hours,
        labor_rate_per_hour=labor_rate_per_hour,
        supply_usages=supply_usages,
        shipping_cost=shipping_cost,
    )


def to_sale_response(sale: Sale) -> SaleResponse:
    return SaleResponse(
        id=sale.id,
        sale_date=sale.sale_date,
        client_name=sale.client_name,
        buyer_name=sale.buyer_name,
        printer_id=sale.printer_id,
        printer_name=sale.printer.name,
        filament_id=sale.filament_id,
        filament_label=f"{sale.filament.brand} {sale.filament.color}" if sale.filament else None,
        grams_used=sale.grams_used,
        print_hours=sale.print_hours,
        postprocess_hours=sale.postprocess_hours,
        base_price=sale.base_price,
        iva_percent=sale.iva_percent,
        iva_amount=sale.iva_amount,
        total_price=sale.total_price,
        material_cost=sale.material_cost,
        depreciation_cost=sale.depreciation_cost,
        energy_cost=sale.energy_cost,
        postprocess_cost=sale.postprocess_cost,
        supplies_cost=sale.supplies_cost,
        shipping_cost=sale.shipping_cost,
        total_cost=sale.total_cost,
        profit=sale.profit,
        margin_percent=sale.margin_percent,
        payment_method=sale.payment_method,
        notes=sale.notes,
        supplies_used=[
            SaleSupplyResponse(
                supply_id=ss.supply_id,
                supply_name=ss.supply.name,
                quantity_used=ss.quantity_used,
                unit_cost_snapshot=ss.unit_cost_snapshot,
            )
            for ss in sale.supplies_used
        ],
    )
