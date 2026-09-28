import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.constants import ELECTRICITY_RATE, LABOR_RATE_PER_HOUR
from app.database import get_db
from app.dependencies import get_current_user, is_watcher, readable_user_ids
from app.models.sale import ORDER_STATUSES, STATUS_CANCELLED, STATUS_DELIVERED, Sale
from app.models.sale_filament import SaleFilament
from app.models.sale_supply import SaleSupply
from app.models.user import User
from app.models.warehouse_item import WarehouseItem
from app.schemas.sale import (
    CalendarOrder,
    CancelOrderRequest,
    DeliveryDateChangeRequest,
    SaleCreateRequest,
    SalePage,
    SaleResponse,
    SaleStatusChangeRequest,
    SaleUpdateRequest,
)
from app.services.audit import log_event
from app.services.calculator import calculate_margin_percent, money
from app.services.cancellation import cancel_order, check_can_delete, undo_remaining_consumption
from app.services.inventory import consume_supply, restore_filament, restore_supply
from app.services.order_status import (
    LOCKED_PRODUCTION_STATUSES,
    OPEN_STATUSES,
    STATUS_LABELS,
    change_status,
    record_status,
    start_as_pending,
)
from app.services.sale_builder import (
    apply_filaments_to_sale,
    build_cost_breakdown,
    can_edit_sale,
    resolve_filaments,
    resolve_printer,
    resolve_sale_owner,
    resolve_supplies,
    sales_editable_by,
    sales_listed_for,
    to_sale_response,
)

router = APIRouter(prefix="/api/sales", tags=["sales"])

# En En producción y Lista la pieza ya se está fabricando: solo se editan estos datos.
EDITABLE_WHILE_IN_PRODUCTION = ("client_name", "buyer_name", "notes", "payment_method", "price", "promised_delivery_date")
LOCKED_FIELD_LABELS = {
    "sale_date": "fecha del pedido",
    "printer_id": "impresora",
    "print_hours": "horas de impresión",
    "postprocess_hours": "horas de postprocesado",
    "shipping_cost": "envío",
    "filaments": "filamentos",
    "supplies": "consumibles",
}


def _sale_query(db: Session):
    return db.query(Sale).options(
        joinedload(Sale.printer),
        joinedload(Sale.filament),
        joinedload(Sale.owner),
        joinedload(Sale.created_by),
        joinedload(Sale.supplies_used).joinedload(SaleSupply.supply),
        joinedload(Sale.filaments_used).joinedload(SaleFilament.filament),
    )


def _get_listed_sale(db: Session, sale_id: uuid.UUID, user: User) -> Sale:
    sale = _sale_query(db).filter(sales_listed_for(db, user), Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venta no encontrada")
    return sale


def _get_editable_sale(db: Session, sale_id: uuid.UUID, user: User) -> Sale:
    """Pedido que el usuario puede modificar. Para un pedido ajeno responde 404 (no se
    revela nada que no pueda tocar)."""
    sale = _sale_query(db).filter(sales_editable_by(user), Sale.id == sale_id).first()
    if sale is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Venta no encontrada")
    if is_watcher(user) and sale.user_id not in readable_user_ids(db, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ya no tienes asignado al dueño de esta venta.")
    return sale


def _parse_status_filter(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    wanted: list[str] = []
    for part in raw.split(","):
        part = part.strip()
        if part == "abiertos":
            wanted.extend(OPEN_STATUSES)
        elif part in ORDER_STATUSES:
            wanted.append(part)
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Estado inválido: {part}")
    return wanted


def _lines(items, key_attr, qty_attr):
    return sorted((str(getattr(i, key_attr)), Decimal(getattr(i, qty_attr)).normalize()) for i in items)


def _locked_changes(sale: Sale, payload: SaleUpdateRequest, changes: dict) -> list[str]:
    """Datos de fabricación que el pedido intenta cambiar (solo cuenta si el valor cambia:
    la app puede reenviar el mismo valor sin que eso sea un cambio)."""
    changed = []
    for field in ("sale_date", "printer_id", "print_hours", "postprocess_hours", "shipping_cost"):
        if field in changes and changes[field] is not None and changes[field] != getattr(sale, field):
            changed.append(field)
    if payload.filaments is not None and "filaments" in payload.model_fields_set:
        if _lines(payload.filaments, "filament_id", "grams_used") != _lines(sale.filaments_used, "filament_id", "grams_used"):
            changed.append("filaments")
    if payload.supplies is not None and "supplies" in payload.model_fields_set:
        if _lines(payload.supplies, "supply_id", "quantity") != _lines(sale.supplies_used, "supply_id", "quantity_used"):
            changed.append("supplies")
    return changed


def _set_price(sale: Sale, price) -> None:
    price = money(price)
    sale.base_price = price
    sale.iva_percent = 0
    sale.iva_amount = 0
    sale.total_price = price


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
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    query = _sale_query(db).filter(sales_listed_for(db, current_user))
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
    statuses = _parse_status_filter(status_filter)
    if statuses is not None:
        query = query.filter(Sale.status.in_(statuses))
    if search is not None:
        like = f"%{search}%"
        query = query.filter(
            (Sale.client_name.ilike(like)) | (Sale.buyer_name.ilike(like)) | (Sale.notes.ilike(like))
        )

    total = query.count()
    rows = query.order_by(Sale.sale_date.desc(), Sale.created_at.desc()).offset(offset).limit(limit).all()
    return SalePage(items=[to_sale_response(s, viewer=current_user) for s in rows], total=total)


@router.get("/calendar", response_model=list[CalendarOrder])
def calendar_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    include_cancelled: bool = Query(default=False),
):
    """Pedidos ubicados en su fecha de entrega comprometida, en un rango de fechas.
    El observador ve los que registró y los de sus usuarios asignados."""
    if date_from is not None and date_to is not None and (date_to - date_from).days > 120:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El rango del calendario no puede superar 120 días.")
    query = (
        db.query(Sale)
        .options(joinedload(Sale.printer), joinedload(Sale.owner), joinedload(Sale.created_by))
        .filter(sales_listed_for(db, current_user))
    )
    if date_from is not None:
        query = query.filter(Sale.promised_delivery_date >= date_from)
    if date_to is not None:
        query = query.filter(Sale.promised_delivery_date <= date_to)
    statuses = _parse_status_filter(status_filter)
    if statuses is not None:
        query = query.filter(Sale.status.in_(statuses))
    elif not include_cancelled:
        query = query.filter(Sale.status != STATUS_CANCELLED)
    rows = query.order_by(Sale.promised_delivery_date, Sale.created_at).limit(2000).all()
    return [
        CalendarOrder(
            id=s.id,
            client_name=s.client_name,
            buyer_name=s.buyer_name,
            status=s.status,
            sale_date=s.sale_date,
            promised_delivery_date=s.promised_delivery_date,
            delivered_date=s.delivered_date,
            price=s.total_price,
            payment_method=s.payment_method,
            printer_name=s.printer.name,
            owner_id=s.user_id,
            owner_username=s.owner.username,
            created_by_username=s.created_by.username if s.created_by is not None else None,
            can_edit=can_edit_sale(s, current_user),
        )
        for s in rows
    ]


@router.patch("/{sale_id}/delivery-date", response_model=SaleResponse)
def change_delivery_date(
    sale_id: uuid.UUID,
    payload: DeliveryDateChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mueve solo la fecha de entrega comprometida (ej. desde el Calendario), sin tocar
    materiales ni recalcular costos. Solo mientras el pedido no esté Entregado ni Cancelado."""
    sale = _get_editable_sale(db, sale_id, current_user)
    if sale.status not in OPEN_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El pedido está {STATUS_LABELS[sale.status]}: ya no tiene fecha de entrega comprometida editable.",
        )
    previous = sale.promised_delivery_date
    if payload.promised_delivery_date != previous:
        sale.promised_delivery_date = payload.promised_delivery_date
        log_event(
            db,
            user_id=current_user.id,
            event_type="SALE_DELIVERY_DATE_CHANGED",
            entity_type="sale",
            entity_id=sale.id,
            details={"promised_delivery_date": {"from": str(previous), "to": str(payload.promised_delivery_date)}},
            ip_address=request.client.host if request.client else None,
        )
        db.commit()
    return to_sale_response(_get_listed_sale(db, sale.id, current_user), viewer=current_user, include_history=True)


@router.get("/{sale_id}", response_model=SaleResponse)
def get_sale(sale_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return to_sale_response(_get_listed_sale(db, sale_id, current_user), viewer=current_user, include_history=True)


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
    # El consumo es igual que siempre (se descuenta al crear); lo que cambia es que el
    # pedido nace Pendiente y no cuenta como ingreso hasta que se entrega.
    start_as_pending(sale, payload.promised_delivery_date)
    db.add(sale)
    db.flush()
    record_status(db, sale, sale.status, current_user, "Pedido creado")

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
            "status": sale.status,
            "promised_delivery_date": sale.promised_delivery_date.isoformat(),
        },
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return to_sale_response(_get_listed_sale(db, sale.id, current_user), exhausted_filaments, viewer=current_user)


@router.put("/{sale_id}", response_model=SaleResponse)
def update_sale(
    sale_id: uuid.UUID,
    payload: SaleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = _get_editable_sale(db, sale_id, current_user)
    changes = payload.model_dump(exclude_unset=True)
    ip = request.client.host if request.client else None

    # ---- Reglas según el estado del pedido ----
    if sale.status == STATUS_CANCELLED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Un pedido cancelado no se puede editar.")
    new_delivered = changes.get("delivered_date")
    if new_delivered is not None and new_delivered != sale.delivered_date and sale.status != STATUS_DELIVERED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha real de entrega solo existe en pedidos entregados.")
    new_promised = changes.get("promised_delivery_date")
    if new_promised is not None and new_promised != sale.promised_delivery_date and sale.status == STATUS_DELIVERED:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Un pedido entregado ya no tiene fecha comprometida editable."
        )
    date_changes = {}
    if new_promised is not None and new_promised != sale.promised_delivery_date:
        date_changes["promised_delivery_date"] = (sale.promised_delivery_date, new_promised)
    if new_delivered is not None and new_delivered != sale.delivered_date:
        date_changes["delivered_date"] = (sale.delivered_date, new_delivered)

    if sale.status in LOCKED_PRODUCTION_STATUSES:
        # En producción / Lista: la pieza ya se está fabricando. No se tocan materiales,
        # horas ni costos; solo datos del pedido y el precio.
        locked = _locked_changes(sale, payload, changes)
        if locked:
            names = ", ".join(LOCKED_FIELD_LABELS[f] for f in locked)
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"El pedido está {STATUS_LABELS[sale.status]}: no se pueden cambiar {names}. "
                "Solo precio, fecha de entrega, trabajo, comprador, método de pago y notas.",
            )
        for field in EDITABLE_WHILE_IN_PRODUCTION:
            if field == "price" or field not in changes:
                continue
            # Comprador y notas se pueden vaciar; el resto de los campos no admite vacío.
            if changes[field] is None and field not in ("buyer_name", "notes"):
                continue
            setattr(sale, field, changes[field])
        if changes.get("price") is not None:
            _set_price(sale, changes["price"])
            sale.profit = money(sale.base_price - sale.total_cost)
            sale.margin_percent = calculate_margin_percent(sale.base_price, sale.total_cost)
        exhausted_filaments = []
    else:
        exhausted_filaments = _update_full(db, sale, payload, changes, current_user)

    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_UPDATED",
        entity_type="sale",
        entity_id=sale.id,
        details={"changes": {k: str(v) for k, v in changes.items()}, "owner_id": str(sale.user_id), "status": sale.status},
        ip_address=ip,
    )
    if date_changes:
        log_event(
            db,
            user_id=current_user.id,
            event_type="SALE_DELIVERY_DATE_CHANGED",
            entity_type="sale",
            entity_id=sale.id,
            details={k: {"from": str(a), "to": str(b)} for k, (a, b) in date_changes.items()},
            ip_address=ip,
        )
    db.commit()
    return to_sale_response(_get_listed_sale(db, sale.id, current_user), exhausted_filaments, viewer=current_user)


def _update_full(db: Session, sale: Sale, payload: SaleUpdateRequest, changes: dict, current_user: User):
    """Edición completa (Pendiente y Entregada): igual que siempre, devuelve lo que usaba
    la venta y vuelve a descontar lo nuevo, recalculando costos."""
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
        _set_price(sale, new_price)
    # Sin precio nuevo, la venta conserva exactamente lo que se cobró (incluidas las
    # ventas antiguas registradas con IVA). La ganancia sale del neto cobrado.
    profit = money(sale.base_price - breakdown.total_cost)
    margin_percent = calculate_margin_percent(sale.base_price, breakdown.total_cost)

    printer.hours_used += new_print_hours

    for field, value in changes.items():
        if field in ("supplies", "filaments", "price"):
            continue
        if field in ("promised_delivery_date", "delivered_date") and value is None:
            continue
        setattr(sale, field, value)

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
    return exhausted_filaments


@router.post("/{sale_id}/status", response_model=SaleResponse)
def change_sale_status(
    sale_id: uuid.UUID,
    payload: SaleStatusChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = _get_editable_sale(db, sale_id, current_user)
    previous = sale.status
    path = change_status(
        db, sale, payload.status, current_user, skip_confirmed=payload.skip_confirmed, today=payload.today or date.today()
    )
    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_STATUS_CHANGED",
        entity_type="sale",
        entity_id=sale.id,
        details={"from": previous, "to": sale.status, "steps": path, "owner_id": str(sale.user_id)},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.expire_all()
    return to_sale_response(_get_listed_sale(db, sale.id, current_user), viewer=current_user, include_history=True)


@router.post("/{sale_id}/cancel", response_model=SaleResponse)
def cancel_sale(
    sale_id: uuid.UUID,
    payload: CancelOrderRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancelar es un hecho del negocio y queda registrado (a diferencia de Eliminar, que
    borra el pedido como si nunca hubiera existido). Los cancelados nunca son ingreso."""
    sale = _get_editable_sale(db, sale_id, current_user)
    previous = sale.status
    piece = cancel_order(
        db,
        sale,
        current_user,
        keep_hours=payload.keep_hours,
        piece_outcome=payload.piece_outcome,
        discard_reason=payload.discard_reason,
        reason=payload.reason,
        today=payload.today or date.today(),
    )
    db.flush()
    ip = request.client.host if request.client else None
    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_CANCELLED",
        entity_type="sale",
        entity_id=sale.id,
        details={
            "from": previous,
            "reason": sale.cancel_reason,
            "keep_hours": not sale.hours_returned,
            "piece_outcome": payload.piece_outcome,
            "loss_amount": str(sale.loss_amount),
            "owner_id": str(sale.user_id),
        },
        ip_address=ip,
    )
    if piece is not None:
        log_event(
            db,
            user_id=current_user.id,
            event_type="WAREHOUSE_ITEM_DISCARDED" if piece.status == "descartada" else "WAREHOUSE_ITEM_CREATED",
            entity_type="warehouse_item",
            entity_id=piece.id,
            details={"name": piece.name, "cost": str(piece.cost), "origin_sale_id": str(sale.id),
                     "discard_reason": piece.discard_reason},
            ip_address=ip,
        )
    db.commit()
    db.expire_all()
    return to_sale_response(_get_listed_sale(db, sale.id, current_user), viewer=current_user, include_history=True)


@router.delete("/{sale_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sale(
    sale_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Eliminar deshace todo, como siempre (para corregir errores). En un pedido
    cancelado solo se devuelve lo que seguía consumido tras la cancelación."""
    sale = _get_editable_sale(db, sale_id, current_user)
    pieces = check_can_delete(db, sale)

    undo_remaining_consumption(sale)
    for piece in pieces:
        db.delete(piece)
    if sale.warehouse_item_id is not None:
        # Borrar la venta de una pieza del Almacén: la pieza vuelve a estar disponible.
        item = db.get(WarehouseItem, sale.warehouse_item_id)
        if item is not None and item.status in ("reservada", "vendida"):
            item.status = "en_almacen"
    db.flush()

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
            "status": sale.status,
        },
        ip_address=request.client.host if request.client else None,
    )
    db.delete(sale)
    db.commit()
