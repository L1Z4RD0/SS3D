import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.dependencies import is_company, is_watcher, readable_user_ids
from app.models.filament import Filament
from app.models.printer import Printer
from app.models.sale import ORDER_STATUSES, Sale
from app.models.sale_filament import SaleFilament
from app.models.supply import Supply
from app.models.user import User
from app.schemas.calculator import FilamentUsageInput, SupplyUsageInput
from app.schemas.sale import (
    ExhaustedFilamentInfo,
    OwnerCostResponse,
    SaleFilamentResponse,
    SalePlateFilamentResponse,
    SalePlateResponse,
    SaleResponse,
    SaleStatusHistoryResponse,
    SaleSupplyResponse,
    WarehousePieceInfo,
)
from app.services.calculator import CostBreakdown, FilamentUsage, SupplyUsage, calculate_costs, money
from app.services.inventory import consume_filament


def sales_counted_for(user: User):
    """Ventas que suman en el Dashboard y el Historial de cada usuario (además, solo las
    Entregadas). Un usuario: las de su inventario, incluidas las que registró un observador
    por él. Un observador: las que registró él, de cualquiera de sus asignados."""
    if is_watcher(user):
        return Sale.created_by_user_id == user.id
    return Sale.user_id == user.id


def sales_listed_for(db: Session, user: User):
    """Pedidos que ve cada usuario en Ventas y el Calendario. El observador ve también los
    pedidos agendados de sus usuarios asignados (los que no registró, solo lectura)."""
    if is_watcher(user):
        return or_(Sale.created_by_user_id == user.id, Sale.user_id.in_(readable_user_ids(db, user)))
    return Sale.user_id == user.id


def sales_editable_by(user: User):
    """Pedidos que cada usuario puede editar, cambiar de estado o eliminar: el dueño todos
    los suyos; el observador solo los que registró él."""
    if is_watcher(user):
        return Sale.created_by_user_id == user.id
    return Sale.user_id == user.id


def can_edit_sale(sale: Sale, viewer: User | None) -> bool:
    if viewer is None:
        return True
    if is_watcher(viewer):
        return sale.created_by_user_id == viewer.id
    return sale.user_id == viewer.id


def sale_resource_owner_ids(db: Session, owner_id: uuid.UUID, seller: User | None) -> list[uuid.UUID]:
    """De quién pueden ser los recursos (filamentos, insumos, planchas) de una venta.

    - Un socio vende solo con lo suyo: no se mezclan inventarios.
    - La Empresa puede combinar lo de todos los socios que observa y lo propio (ej. impresora
      de Diego + filamento de Sntg + insumos de la Empresa). Cada costo queda a cuenta del dueño
      de cada recurso (ver cost_allocation) y la app avisa que se mezclan dueños."""
    ids = [owner_id]
    if is_company(seller):
        ids += [uid for uid in readable_user_ids(db, seller) if uid != owner_id]
    return ids


def resolve_sale_owner(db: Session, user: User, owner_id: uuid.UUID | None) -> uuid.UUID:
    """Dueño del inventario con que se registra una venta. Un usuario normal solo vende
    lo suyo; un observador debe elegir a uno de los usuarios que tiene asignados."""
    if not is_watcher(user):
        if owner_id is not None and owner_id != user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes registrar ventas con tu propio inventario.")
        return user.id
    if owner_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Selecciona el usuario para el que registras la venta.")
    if owner_id not in readable_user_ids(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No tienes asignado a ese usuario.")
    return owner_id


def resolve_printer(
    db: Session, user: User, printer_id: uuid.UUID, allowed_user_ids: list[uuid.UUID] | None = None
) -> Printer:
    # readable_user_ids: para un usuario normal es solo el suyo; para un watcher son
    # los usuarios que el admin le asignó. Al registrar una venta se restringe al dueño
    # de la venta (allowed_user_ids), para que no se mezclen inventarios.
    allowed_ids = allowed_user_ids if allowed_user_ids is not None else readable_user_ids(db, user)
    printer = db.query(Printer).filter(Printer.id == printer_id, Printer.user_id.in_(allowed_ids)).first()
    if printer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Impresora no encontrada")
    return printer


def resolve_filaments(
    db: Session,
    user: User,
    usages: list[FilamentUsageInput],
    allowed_user_ids: list[uuid.UUID] | None = None,
) -> list[tuple[Filament, Decimal]]:
    allowed_ids = allowed_user_ids if allowed_user_ids is not None else readable_user_ids(db, user)
    resolved: list[tuple[Filament, Decimal]] = []
    for usage in usages:
        filament = (
            db.query(Filament)
            .filter(Filament.id == usage.filament_id, Filament.user_id.in_(allowed_ids))
            .first()
        )
        if filament is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Filamento {usage.filament_id} no encontrado")
        resolved.append((filament, usage.grams_used))
    return resolved


def resolve_supplies(
    db: Session,
    user: User,
    usages: list[SupplyUsageInput],
    allowed_user_ids: list[uuid.UUID] | None = None,
) -> list[tuple[Supply, Decimal]]:
    allowed_ids = allowed_user_ids if allowed_user_ids is not None else readable_user_ids(db, user)
    resolved: list[tuple[Supply, Decimal]] = []
    for usage in usages:
        supply = (
            db.query(Supply).filter(Supply.id == usage.supply_id, Supply.user_id.in_(allowed_ids)).first()
        )
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


def _cost_allocation_fields(sale: Sale) -> dict:
    # Import local: cost_allocation importa modelos que importan este módulo indirectamente.
    from app.services.cost_allocation import allocate_sale_costs

    allocation = allocate_sale_costs(sale)
    return {
        "cost_by_owner": [
            OwnerCostResponse(
                user_id=o.user_id, username=o.username, machine=o.machine, material=o.material,
                supplies=o.supplies, total=o.total,
            )
            for o in allocation.owners
        ],
        "shared_cost": allocation.shared,
    }


def to_sale_response(
    sale: Sale,
    exhausted_filaments: list[Filament] | None = None,
    viewer: User | None = None,
    include_history: bool = False,
) -> SaleResponse:
    history = []
    if include_history:
        history = [
            SaleStatusHistoryResponse(
                status=h.status,
                changed_at=h.changed_at,
                changed_by_username=h.changed_by.username if h.changed_by is not None else None,
                note=h.note,
                is_migration=h.is_migration,
            )
            # Los pasos de una entrega directa tienen la misma hora: desempata el orden natural.
            for h in sorted(sale.status_history, key=lambda h: (h.changed_at, ORDER_STATUSES.index(h.status)))
        ]
    piece = None
    if include_history and sale.origin_pieces:
        p = sale.origin_pieces[0]
        piece = WarehousePieceInfo(id=p.id, status=p.status, cost=p.cost, price=p.price)
    return SaleResponse(
        cancel_reason=sale.cancel_reason,
        loss_amount=sale.loss_amount,
        warehouse_piece=piece,
        status=sale.status,
        promised_delivery_date=sale.promised_delivery_date,
        delivered_date=sale.delivered_date,
        warehouse_item_id=sale.warehouse_item_id,
        can_edit=can_edit_sale(sale, viewer),
        has_provisional_costs=any(ss.pending_qty > 0 for ss in sale.supplies_used),
        risk_percent=sale.risk_percent,
        risk_amount=sale.risk_amount,
        delivery_by=sale.delivery_by,
        delivery_amount=sale.shipping_cost,
        **_cost_allocation_fields(sale),
        plates=[
            SalePlateResponse(
                id=p.id,
                name=p.name,
                printer_id=p.printer_id,
                printer_name=p.printer.name,
                print_hours=p.print_hours,
                is_reprint=p.is_reprint,
                material_cost=p.material_cost,
                depreciation_cost=p.depreciation_cost,
                energy_cost=p.energy_cost,
                total_cost=p.total_cost,
                filaments=[
                    SalePlateFilamentResponse(
                        filament_id=pf.filament_id, filament_label=_filament_label(pf.filament), grams_used=pf.grams_used
                    )
                    for pf in p.filaments_used
                ],
            )
            for p in sale.plates
        ],
        reprint_cost=sum((p.total_cost for p in sale.plates if p.is_reprint), Decimal(0)),
        status_history=history,
        id=sale.id,
        sale_date=sale.sale_date,
        client_name=sale.client_name,
        buyer_name=sale.buyer_name,
        owner_id=sale.user_id,
        owner_username=sale.owner.username,
        created_by_user_id=sale.created_by_user_id,
        created_by_username=sale.created_by.username if sale.created_by is not None else None,
        printer_id=sale.printer_id,
        printer_name=sale.printer.name,
        filament_id=sale.filament_id,
        filament_label=_build_filament_label(sale),
        grams_used=sale.grams_used,
        print_hours=sale.print_hours,
        postprocess_hours=sale.postprocess_hours,
        # total_price: lo que se cobró. En ventas antiguas registradas con IVA incluye
        # ese IVA; en las nuevas es igual a base_price (la app ya no calcula IVA).
        price=sale.total_price,
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
                pending_qty=ss.pending_qty,
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
