import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.constants import ELECTRICITY_RATE, LABOR_RATE_PER_HOUR
from app.database import get_db
from app.dependencies import get_current_user, is_watcher, readable_user_ids
from app.models.sale import Sale
from app.models.sale_filament import SaleFilament
from app.models.sale_supply import SaleSupply
from app.models.user import User
from app.schemas.sale import SaleCreateRequest, SalePage, SaleResponse, SaleUpdateRequest
from app.services.audit import log_event
from app.services.calculator import calculate_margin_percent, money
from app.services.inventory import consume_supply, restore_filament, restore_supply
from app.services.order_status import record_status, start_as_delivered, sync_legacy_dates
from app.services.sale_builder import (
    apply_filaments_to_sale,
    build_cost_breakdown,
    resolve_filaments,
    resolve_printer,
    resolve_sale_owner,
    resolve_supplies,
    sales_visible_to,
    to_sale_response,
)

router = APIRouter(prefix="/api/sales", tags=["sales"])


def _sale_query(db: Session, user: User):
    return (
        db.query(Sale)
        .options(
            joinedload(Sale.printer),
            joinedload(Sale.filament),
            joinedload(Sale.owner),
            joinedload(Sale.created_by),
            joinedload(Sale.supplies_used).joinedload(SaleSupply.supply),
            joinedload(Sale.filaments_used).joinedload(SaleFilament.filament),
        )
        .filter(sales_visible_to(user))
    )


def _get_visible_sale(db: Session, sale_id: uuid.UUID, user: User) -> Sale:
    sale = _sale_query(db, user).filter(Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venta no encontrada")
    return sale


def _require_still_assigned(db: Session, user: User, sale: Sale) -> None:
    """Un observador solo puede tocar ventas de usuarios que todavía tiene asignados."""
    if is_watcher(user) and sale.user_id not in readable_user_ids(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ya no tienes asignado al dueño de esta venta.")


@router.get("", response_model=SalePage)
def list_sales(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    client: str | None = Query(default=None),
    printer_id: uuid.UUID | None = Query(default=None),
    payment_method: str | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = _sale_query(db, current_user)
    if date_from is not None:
        query = query.filter(Sale.sale_date >= date_from)
    if date_to is not None:
        query = query.filter(Sale.sale_date <= date_to)
    if client is not None:
        query = query.filter(Sale.client_name.ilike(f"%{client}%"))
    if printer_id is not None:
        query = query.filter(Sale.printer_id == printer_id)
    if payment_method is not None:
        query = query.filter(Sale.payment_method == payment_method)
    if search is not None:
        like = f"%{search}%"
        query = query.filter(
            (Sale.client_name.ilike(like)) | (Sale.buyer_name.ilike(like)) | (Sale.notes.ilike(like))
        )

    total = query.count()
    rows = query.order_by(Sale.sale_date.desc(), Sale.created_at.desc()).offset(offset).limit(limit).all()
    return SalePage(items=[to_sale_response(s) for s in rows], total=total)


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return to_sale_response(_get_visible_sale(db, sale_id, current_user))


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # La venta usa solo el inventario de un dueño: el propio usuario, o el usuario
    # asignado que eligió el observador. Así los inventarios nunca se mezclan.
    owner_id = resolve_sale_owner(db, current_user, payload.owner_id)
    printer = resolve_printer(db, current_user, payload.printer_id, [owner_id])
    resolved_filaments = resolve_filaments(db, current_user, payload.filaments, [owner_id])
    resolved_supplies = resolve_supplies(db, current_user, payload.supplies, [owner_id])

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

    price = money(payload.price)
    printer.hours_used += payload.print_hours

    sale = Sale(
        user_id=owner_id,
        created_by_user_id=current_user.id,
        sale_date=payload.sale_date,
        client_name=payload.client_name,
        buyer_name=payload.buyer_name,
        printer_id=printer.id,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        # Sin IVA: lo cobrado es el precio. Las columnas de IVA quedan en 0 (se conservan
        # por las ventas antiguas registradas con IVA).
        base_price=price,
        iva_percent=0,
        iva_amount=0,
        total_price=price,
        material_cost=breakdown.material_cost,
        depreciation_cost=breakdown.depreciation_cost,
        energy_cost=breakdown.energy_cost,
        postprocess_cost=breakdown.postprocess_cost,
        supplies_cost=breakdown.supplies_cost,
        shipping_cost=breakdown.shipping_cost,
        total_cost=breakdown.total_cost,
        profit=money(price - breakdown.total_cost),
        margin_percent=calculate_margin_percent(price, breakdown.total_cost),
        payment_method=payload.payment_method,
        notes=payload.notes,
    )
    start_as_delivered(sale)
    db.add(sale)
    db.flush()
    record_status(db, sale, sale.status, current_user, "Venta registrada")

    exhausted_filaments = apply_filaments_to_sale(db, sale, resolved_filaments)

    for supply, qty in resolved_supplies:
        consume_supply(supply, qty)
        db.add(SaleSupply(sale_id=sale.id, supply_id=supply.id, quantity_used=qty, unit_cost_snapshot=supply.unit_cost or 0))

    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_CREATED",
        entity_type="sale",
        entity_id=sale.id,
        details={
            "source": "manual",
            "client_name": sale.client_name,
            "price": str(price),
            "owner_id": str(owner_id),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return to_sale_response(_get_visible_sale(db, sale.id, current_user), exhausted_filaments)


@router.put("/{sale_id}", response_model=SaleResponse)
def update_sale(
    sale_id: uuid.UUID,
    payload: SaleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = _get_visible_sale(db, sale_id, current_user)
    _require_still_assigned(db, current_user, sale)
    # El dueño de una venta no cambia al editarla: sus recursos siguen siendo los suyos.
    owner_ids = [sale.user_id]

    old_printer = sale.printer
    old_filament_rows = list(sale.filaments_used)
    old_supply_rows = list(sale.supplies_used)

    # Reverse previous inventory impact
    old_printer.hours_used -= sale.print_hours
    for sf in old_filament_rows:
        restore_filament(sf.filament, sf.grams_used)
        db.delete(sf)
    for ss in old_supply_rows:
        restore_supply(ss.supply, ss.quantity_used)
        db.delete(ss)
    db.flush()

    changes = payload.model_dump(exclude_unset=True)

    new_printer_id = changes.get("printer_id", sale.printer_id)
    new_print_hours = changes.get("print_hours", sale.print_hours)
    new_postprocess_hours = changes.get("postprocess_hours", sale.postprocess_hours)
    new_shipping_cost = changes.get("shipping_cost", sale.shipping_cost)
    new_price = changes.get("price")
    # payload.filaments/supplies are typed Pydantic objects; model_dump() would
    # have flattened them into plain dicts, so read them straight off the payload.
    new_filaments = payload.filaments if "filaments" in payload.model_fields_set else None
    new_supplies = payload.supplies if "supplies" in payload.model_fields_set else None

    printer = resolve_printer(db, current_user, new_printer_id, owner_ids)
    resolved_supplies = (
        resolve_supplies(db, current_user, new_supplies, owner_ids)
        if new_supplies is not None
        else [(ss.supply, ss.quantity_used) for ss in old_supply_rows]
    )
    resolved_filaments = (
        resolve_filaments(db, current_user, new_filaments, owner_ids)
        if new_filaments is not None
        else [(sf.filament, sf.grams_used) for sf in old_filament_rows]
    )

    breakdown = build_cost_breakdown(
        printer=printer,
        resolved_filaments=resolved_filaments,
        resolved_supplies=resolved_supplies,
        print_hours=new_print_hours,
        postprocess_hours=new_postprocess_hours,
        shipping_cost=new_shipping_cost,
        electricity_rate=ELECTRICITY_RATE,
        labor_rate_per_hour=LABOR_RATE_PER_HOUR,
    )

    if new_price is not None:
        price = money(new_price)
        sale.base_price = price
        sale.iva_percent = 0
        sale.iva_amount = 0
        sale.total_price = price
    # Sin precio nuevo, la venta conserva exactamente lo que se cobró (incluidas las
    # ventas antiguas registradas con IVA). La ganancia sale del neto cobrado.
    profit = money(sale.base_price - breakdown.total_cost)
    margin_percent = calculate_margin_percent(sale.base_price, breakdown.total_cost)

    printer.hours_used += new_print_hours

    for field, value in changes.items():
        if field in ("supplies", "filaments", "price"):
            continue
        setattr(sale, field, value)

    sync_legacy_dates(sale)
    sale.printer_id = printer.id
    sale.print_hours = new_print_hours
    sale.postprocess_hours = new_postprocess_hours
    sale.shipping_cost = new_shipping_cost
    sale.material_cost = breakdown.material_cost
    sale.depreciation_cost = breakdown.depreciation_cost
    sale.energy_cost = breakdown.energy_cost
    sale.postprocess_cost = breakdown.postprocess_cost
    sale.supplies_cost = breakdown.supplies_cost
    sale.total_cost = breakdown.total_cost
    sale.profit = profit
    sale.margin_percent = margin_percent

    exhausted_filaments = apply_filaments_to_sale(db, sale, resolved_filaments)

    for supply, qty in resolved_supplies:
        consume_supply(supply, qty)
        db.add(SaleSupply(sale_id=sale.id, supply_id=supply.id, quantity_used=qty, unit_cost_snapshot=supply.unit_cost or 0))

    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_UPDATED",
        entity_type="sale",
        entity_id=sale.id,
        details={"changes": {k: str(v) for k, v in changes.items()}, "owner_id": str(sale.user_id)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return to_sale_response(_get_visible_sale(db, sale.id, current_user), exhausted_filaments)


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(
    sale_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = _get_visible_sale(db, sale_id, current_user)
    _require_still_assigned(db, current_user, sale)

    sale.printer.hours_used -= sale.print_hours
    for sf in sale.filaments_used:
        restore_filament(sf.filament, sf.grams_used)
    for ss in sale.supplies_used:
        restore_supply(ss.supply, ss.quantity_used)

    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_DELETED",
        entity_type="sale",
        entity_id=sale.id,
        details={
            "client_name": sale.client_name,
            "sale_date": sale.sale_date.isoformat(),
            "price": str(sale.total_price),
            "owner_id": str(sale.user_id),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.delete(sale)
    db.commit()
