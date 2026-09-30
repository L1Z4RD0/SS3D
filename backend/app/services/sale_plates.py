"""Planchas adicionales de un pedido.

La plancha principal son la impresora, horas y filamentos de la propia venta (así los
pedidos de una sola plancha funcionan igual que siempre). Cada plancha adicional tiene su
impresora, horas y filamentos; sus costos (material, depreciación, energía) se guardan en
la plancha y se suman a los de la venta. Una reimpresión por fallo es una plancha más:
suma costo, pero no cambia el precio.
"""
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy.orm import Session

from app.constants import ELECTRICITY_RATE, LABOR_RATE_PER_HOUR
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import Sale
from app.models.sale_plate import SalePlate, SalePlateFilament
from app.models.user import User
from app.schemas.calculator import PlateInput
from app.services.calculator import CostBreakdown, calculate_margin_percent, money
from app.services.inventory import consume_filament, restore_filament
from app.services.sale_builder import build_cost_breakdown, filament_line_cost, resolve_filaments, resolve_printer


@dataclass
class ResolvedPlate:
    name: str
    printer: Printer
    filaments: list[tuple[Filament, Decimal]]
    print_hours: Decimal
    is_reprint: bool
    costs: CostBreakdown


def resolve_plates(
    db: Session,
    user: User,
    plates: list[PlateInput],
    allowed_user_ids: list[uuid.UUID] | None = None,
    is_reprint: bool = False,
) -> list[ResolvedPlate]:
    resolved = []
    for plate in plates:
        printer = resolve_printer(db, user, plate.printer_id, allowed_user_ids)
        filaments = resolve_filaments(db, user, plate.filaments, allowed_user_ids)
        costs = build_cost_breakdown(
            printer=printer,
            resolved_filaments=filaments,
            resolved_supplies=[],
            print_hours=plate.print_hours,
            postprocess_hours=Decimal(0),
            shipping_cost=Decimal(0),
            electricity_rate=ELECTRICITY_RATE,
            labor_rate_per_hour=LABOR_RATE_PER_HOUR,
        )
        resolved.append(ResolvedPlate(plate.name.strip(), printer, filaments, plate.print_hours, is_reprint, costs))
    return resolved


def _plus_plate_costs(breakdown: CostBreakdown, material: Decimal, depreciation: Decimal, energy: Decimal) -> CostBreakdown:
    # Material, depreciación y energía de las planchas son parte de la base del margen,
    # igual que los de la plancha principal.
    added = material + depreciation + energy
    return replace(
        breakdown,
        material_cost=money(breakdown.material_cost + material),
        depreciation_cost=money(breakdown.depreciation_cost + depreciation),
        energy_cost=money(breakdown.energy_cost + energy),
        margin_base_cost=money(breakdown.margin_base_cost + added),
        total_cost=money(breakdown.total_cost + added),
    )


def with_new_plates(breakdown: CostBreakdown, plates: list[ResolvedPlate]) -> CostBreakdown:
    """Costo del pedido completo: plancha principal + planchas que se van a registrar."""
    return _plus_plate_costs(
        breakdown,
        sum((p.costs.material_cost for p in plates), Decimal(0)),
        sum((p.costs.depreciation_cost for p in plates), Decimal(0)),
        sum((p.costs.energy_cost for p in plates), Decimal(0)),
    )


def with_stored_plates(breakdown: CostBreakdown, plates: list[SalePlate]) -> CostBreakdown:
    """Igual, pero con las planchas ya registradas (al recalcular una venta editada)."""
    return _plus_plate_costs(
        breakdown,
        sum((p.material_cost for p in plates), Decimal(0)),
        sum((p.depreciation_cost for p in plates), Decimal(0)),
        sum((p.energy_cost for p in plates), Decimal(0)),
    )


def plates_grams(plates) -> Decimal:
    return money(sum((pf.grams_used for p in plates for pf in p.filaments_used), Decimal(0)))


def apply_plates(db: Session, sale: Sale, plates: list[ResolvedPlate]) -> list[Filament]:
    """Descuenta filamento y suma horas a cada impresora, y registra las planchas. Los
    costos de la venta NO se tocan aquí (al crear ya vienen incluidos). Devuelve los
    filamentos que quedaron agotados."""
    exhausted: list[Filament] = []
    for rp in plates:
        plate = SalePlate(
            sale_id=sale.id,
            name=rp.name,
            printer_id=rp.printer.id,
            print_hours=rp.print_hours,
            is_reprint=rp.is_reprint,
            material_cost=rp.costs.material_cost,
            depreciation_cost=rp.costs.depreciation_cost,
            energy_cost=rp.costs.energy_cost,
        )
        db.add(plate)
        db.flush()
        rp.printer.hours_used += rp.print_hours
        for filament, grams in rp.filaments:
            consume_filament(filament, grams)
            if filament.available_g <= 0 and filament not in exhausted:
                exhausted.append(filament)
            db.add(SalePlateFilament(
                plate_id=plate.id,
                filament_id=filament.id,
                grams_used=grams,
                material_cost_snapshot=filament_line_cost(filament, grams),
            ))
            sale.grams_used = money(sale.grams_used + grams)
    return exhausted


def _shift_sale_costs(sale: Sale, material: Decimal, depreciation: Decimal, energy: Decimal) -> None:
    added = material + depreciation + energy
    sale.material_cost = money(sale.material_cost + material)
    sale.depreciation_cost = money(sale.depreciation_cost + depreciation)
    sale.energy_cost = money(sale.energy_cost + energy)
    sale.total_cost = money(sale.total_cost + added)
    # El precio no cambia: la plancha extra (o la reimpresión) se come la ganancia.
    sale.profit = money(sale.profit - added)
    sale.margin_percent = calculate_margin_percent(sale.base_price, sale.total_cost)


def add_plate(db: Session, sale: Sale, plate: ResolvedPlate) -> list[Filament]:
    """Agrega una plancha (o reimpresión) a un pedido ya registrado."""
    exhausted = apply_plates(db, sale, [plate])
    _shift_sale_costs(sale, plate.costs.material_cost, plate.costs.depreciation_cost, plate.costs.energy_cost)
    return exhausted


def remove_plate(db: Session, sale: Sale, plate: SalePlate) -> None:
    """Quita una plancha: devuelve su filamento y sus horas (si el pedido todavía los tiene
    consumidos) y descuenta su costo de la venta."""
    grams = plates_grams([plate])
    if not sale.materials_returned:
        for pf in plate.filaments_used:
            restore_filament(pf.filament, pf.grams_used)
    if not sale.hours_returned:
        plate.printer.hours_used -= plate.print_hours
    sale.grams_used = money(sale.grams_used - grams)
    _shift_sale_costs(sale, -plate.material_cost, -plate.depreciation_cost, -plate.energy_cost)
    db.delete(plate)


def return_plates_materials(sale: Sale) -> None:
    for plate in sale.plates:
        for pf in plate.filaments_used:
            restore_filament(pf.filament, pf.grams_used)


def return_plates_hours(sale: Sale) -> None:
    for plate in sale.plates:
        plate.printer.hours_used -= plate.print_hours
