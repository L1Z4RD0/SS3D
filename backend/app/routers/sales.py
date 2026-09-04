import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.sale import Sale
from app.models.sale_supply import SaleSupply
from app.models.user import User
from app.schemas.sale import SaleCreateRequest, SalePage, SaleResponse, SaleUpdateRequest
from app.services.audit import log_event
from app.services.calculator import calculate_margin_percent, money
from app.services.inventory import consume_filament, consume_supply, restore_filament, restore_supply
from app.services.sale_builder import (
    build_cost_breakdown,
    resolve_filament,
    resolve_printer,
    resolve_supplies,
    to_sale_response,
)
from app.services.settings import get_or_create_settings

router = APIRouter(prefix="/api/sales", tags=["sales"])


def _sale_query(db: Session, user: User):
    return (
        db.query(Sale)
        .options(
            joinedload(Sale.printer),
            joinedload(Sale.filament),
            joinedload(Sale.supplies_used).joinedload(SaleSupply.supply),
        )
        .filter(Sale.user_id == user.id)
    )


def _get_owned_sale(db: Session, sale_id: uuid.UUID, user: User) -> Sale:
    sale = _sale_query(db, user).filter(Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venta no encontrada")
    return sale


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
    sale = _get_owned_sale(db, sale_id, current_user)
    return to_sale_response(sale)


@router.post("", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def create_sale(
    payload: SaleCreateRequest,
    request: Request,
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

    iva_percent = payload.iva_percent if payload.iva_percent is not None else settings.iva_percent
    base_price = money(payload.base_price)
    iva_amount = money(base_price * iva_percent / 100)
    total_price = money(base_price + iva_amount)
    profit = money(base_price - breakdown.total_cost)
    margin_percent = calculate_margin_percent(base_price, breakdown.total_cost)

    if filament is not None:
        consume_filament(filament, payload.grams_used)
    printer.hours_used += payload.print_hours

    sale = Sale(
        user_id=current_user.id,
        sale_date=payload.sale_date,
        client_name=payload.client_name,
        buyer_name=payload.buyer_name,
        printer_id=printer.id,
        filament_id=filament.id if filament else None,
        grams_used=payload.grams_used,
        print_hours=payload.print_hours,
        postprocess_hours=payload.postprocess_hours,
        base_price=base_price,
        iva_percent=iva_percent,
        iva_amount=iva_amount,
        total_price=total_price,
        material_cost=breakdown.material_cost,
        depreciation_cost=breakdown.depreciation_cost,
        energy_cost=breakdown.energy_cost,
        postprocess_cost=breakdown.postprocess_cost,
        supplies_cost=breakdown.supplies_cost,
        shipping_cost=breakdown.shipping_cost,
        total_cost=breakdown.total_cost,
        profit=profit,
        margin_percent=margin_percent,
        payment_method=payload.payment_method,
        notes=payload.notes,
    )
    db.add(sale)
    db.flush()

    for supply, qty in resolved_supplies:
        consume_supply(supply, qty)
        db.add(SaleSupply(sale_id=sale.id, supply_id=supply.id, quantity_used=qty, unit_cost_snapshot=supply.unit_cost or 0))

    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_CREATED",
        entity_type="sale",
        entity_id=sale.id,
        details={"source": "manual", "client_name": sale.client_name, "total_price": str(sale.total_price)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return to_sale_response(_get_owned_sale(db, sale.id, current_user))


@router.put("/{sale_id}", response_model=SaleResponse)
def update_sale(
    sale_id: uuid.UUID,
    payload: SaleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = _get_owned_sale(db, sale_id, current_user)
    settings = get_or_create_settings(db, current_user.id)

    old_printer = sale.printer
    old_filament = sale.filament
    old_supply_rows = list(sale.supplies_used)

    # Reverse previous inventory impact
    old_printer.hours_used -= sale.print_hours
    if old_filament is not None:
        restore_filament(old_filament, sale.grams_used)
    for ss in old_supply_rows:
        restore_supply(ss.supply, ss.quantity_used)
        db.delete(ss)
    db.flush()

    changes = payload.model_dump(exclude_unset=True)

    new_printer_id = changes.get("printer_id", sale.printer_id)
    new_filament_id = changes.get("filament_id", sale.filament_id)
    new_grams_used = changes.get("grams_used", sale.grams_used)
    new_print_hours = changes.get("print_hours", sale.print_hours)
    new_postprocess_hours = changes.get("postprocess_hours", sale.postprocess_hours)
    new_shipping_cost = changes.get("shipping_cost", sale.shipping_cost)
    new_base_price = changes.get("base_price", sale.base_price)
    new_iva_percent = changes.get("iva_percent", sale.iva_percent)
    new_supplies = changes.get("supplies", None)

    printer = resolve_printer(db, current_user, new_printer_id)
    filament = resolve_filament(db, current_user, new_filament_id)
    resolved_supplies = (
        resolve_supplies(db, current_user, new_supplies)
        if new_supplies is not None
        else [(ss.supply, ss.quantity_used) for ss in old_supply_rows]
    )

    breakdown = build_cost_breakdown(
        printer=printer,
        filament=filament,
        resolved_supplies=resolved_supplies,
        grams_used=new_grams_used,
        print_hours=new_print_hours,
        postprocess_hours=new_postprocess_hours,
        shipping_cost=new_shipping_cost,
        electricity_rate=settings.electricity_rate,
        labor_rate_per_hour=settings.labor_rate_per_hour,
    )

    base_price = money(new_base_price)
    iva_amount = money(base_price * new_iva_percent / 100)
    total_price = money(base_price + iva_amount)
    profit = money(base_price - breakdown.total_cost)
    margin_percent = calculate_margin_percent(base_price, breakdown.total_cost)

    if filament is not None:
        consume_filament(filament, new_grams_used)
    printer.hours_used += new_print_hours

    for field, value in changes.items():
        if field == "supplies":
            continue
        setattr(sale, field, value)

    sale.printer_id = printer.id
    sale.filament_id = filament.id if filament else None
    sale.grams_used = new_grams_used
    sale.print_hours = new_print_hours
    sale.postprocess_hours = new_postprocess_hours
    sale.shipping_cost = new_shipping_cost
    sale.base_price = base_price
    sale.iva_percent = new_iva_percent
    sale.iva_amount = iva_amount
    sale.total_price = total_price
    sale.material_cost = breakdown.material_cost
    sale.depreciation_cost = breakdown.depreciation_cost
    sale.energy_cost = breakdown.energy_cost
    sale.postprocess_cost = breakdown.postprocess_cost
    sale.supplies_cost = breakdown.supplies_cost
    sale.total_cost = breakdown.total_cost
    sale.profit = profit
    sale.margin_percent = margin_percent

    for supply, qty in resolved_supplies:
        consume_supply(supply, qty)
        db.add(SaleSupply(sale_id=sale.id, supply_id=supply.id, quantity_used=qty, unit_cost_snapshot=supply.unit_cost or 0))

    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_UPDATED",
        entity_type="sale",
        entity_id=sale.id,
        details={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return to_sale_response(_get_owned_sale(db, sale.id, current_user))


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(
    sale_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = _get_owned_sale(db, sale_id, current_user)

    sale.printer.hours_used -= sale.print_hours
    if sale.filament is not None:
        restore_filament(sale.filament, sale.grams_used)
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
            "total_price": str(sale.total_price),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.delete(sale)
    db.commit()
