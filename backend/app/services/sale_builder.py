import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import Sale
from app.models.sale_filament import SaleFilament
from app.models.supply import Supply
from app.models.user import User
from app.schemas.calculator import FilamentUsageInput, SupplyUsageInput
from app.schemas.sale import ExhaustedFilamentInfo, SaleFilamentResponse, SaleResponse, SaleSupplyResponse
from app.services.calculator import CostBreakdown, FilamentUsage, SupplyUsage, calculate_costs, money
from app.services.inventory import consume_filament


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


def resolve_filaments(
    db: Session, user: User, usages: list[FilamentUsageInput]
) -> list[tuple[Filament, Decimal]]:
    resolved: list[tuple[Filament, Decimal]] = []
    for usage in usages:
        filament = (
            db.query(Filament).filter(Filament.id == usage.filament_id, Filament.user_id == user.id).first()
        )
        if filament is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Filamento {usage.filament_id} no encontrado")
        resolved.append((filament, usage.grams_used))
    return resolved


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


def filament_line_cost(filament: Filament, grams: Decimal) -> Decimal:
    return FilamentUsage(
        filament_id=filament.id,
        grams_used=grams,
        spool_weight_g=filament.spool_weight_g,
        spool_price=filament.spool_price,
    ).material_cost


def build_cost_breakdown(
    *,
    printer: Printer,
    resolved_filaments: list[tuple[Filament, Decimal]],
    resolved_supplies: list[tuple[Supply, Decimal]],
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
    filament_usages = [
        FilamentUsage(
            filament_id=filament.id,
            grams_used=grams,
            spool_weight_g=filament.spool_weight_g,
            spool_price=filament.spool_price,
        )
        for filament, grams in resolved_filaments
    ]
    return calculate_costs(
        filament_usages=filament_usages,
        print_hours=print_hours,
        depreciation_cost_per_hour=printer.depreciation_cost_per_hour,
        power_kw=printer.power_kw,
        electricity_rate=electricity_rate,
        postprocess_hours=postprocess_hours,
        labor_rate_per_hour=labor_rate_per_hour,
        supply_usages=supply_usages,
        shipping_cost=shipping_cost,
    )


def _filament_label(filament: Filament) -> str:
    if filament.sku:
        return f"{filament.brand} {filament.color} ({filament.sku})"
    return f"{filament.brand} {filament.color}"


def _build_filament_label(sale: Sale) -> str | None:
    if sale.filament is not None:
        return _filament_label(sale.filament)
    labels = [_filament_label(sf.filament) for sf in sale.filaments_used]
    if not labels:
        return None
    if len(labels) <= 3:
        return " + ".join(labels)
    return f"Multicolor ({len(labels)} filamentos)"


def apply_filaments_to_sale(
    db: Session, sale: Sale, resolved_filaments: list[tuple[Filament, Decimal]]
) -> list[Filament]:
    """Consume stock for each filament line and create the sale_filaments rows.
    Also sets sale.filament_id (only when exactly one filament) and sale.grams_used (aggregate).
    Returns the filaments that were left at 0g or below by this consumption (a filament can only
    reach that state here, since consume_filament already blocks consuming past what's available)."""
    total_grams = money(sum((grams for _, grams in resolved_filaments), Decimal(0)))
    sale.grams_used = total_grams
    sale.filament_id = resolved_filaments[0][0].id if len(resolved_filaments) == 1 else None

    exhausted: list[Filament] = []
    for filament, grams in resolved_filaments:
        consume_filament(filament, grams)
        if filament.available_g <= 0:
            exhausted.append(filament)
        db.add(
            SaleFilament(
                sale_id=sale.id,
                filament_id=filament.id,
                grams_used=grams,
                material_cost_snapshot=filament_line_cost(filament, grams),
            )
        )
    return exhausted


def to_sale_response(sale: Sale, exhausted_filaments: list[Filament] | None = None) -> SaleResponse:
    return SaleResponse(
        id=sale.id,
        sale_date=sale.sale_date,
        client_name=sale.client_name,
        buyer_name=sale.buyer_name,
        printer_id=sale.printer_id,
        printer_name=sale.printer.name,
        filament_id=sale.filament_id,
        filament_label=_build_filament_label(sale),
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
        filaments_used=[
            SaleFilamentResponse(
                filament_id=sf.filament_id,
                filament_label=_filament_label(sf.filament),
                grams_used=sf.grams_used,
                material_cost_snapshot=sf.material_cost_snapshot,
            )
            for sf in sale.filaments_used
        ],
        exhausted_filaments=[
            ExhaustedFilamentInfo(filament_id=f.id, filament_label=_filament_label(f))
            for f in (exhausted_filaments or [])
        ],
    )
