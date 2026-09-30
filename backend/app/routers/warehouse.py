"""Almacén: piezas de pedidos cancelados que siguen en poder del negocio.

- El dueño ve, edita (nombre, precio, notas), descarta y vende sus piezas.
- El observador ve las piezas de sus usuarios asignados, separadas por dueño, y puede
  venderlas ("Venta para" el dueño, "Registrada por" él), pero no editarlas ni descartarlas.
"""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user, is_watcher, readable_user_ids
from app.models.base import utcnow
from app.models.sale import STATUS_CANCELLED, STATUS_READY, Sale
from app.models.user import User
from app.models.warehouse_item import (
    ITEM_DISCARDED,
    ITEM_IN_STOCK,
    ITEM_RESERVED,
    WAREHOUSE_ITEM_STATUSES,
    WarehouseItem,
)
from app.schemas.sale import GIFT_PAYMENT_METHOD, SaleResponse
from app.schemas.warehouse import (
    WarehouseDiscardRequest,
    WarehouseItemResponse,
    WarehouseItemUpdateRequest,
    WarehouseSellRequest,
)
from app.services.audit import log_event
from app.services.calculator import calculate_margin_percent, money
from app.services.discord import announce_order
from app.services.order_status import record_status
from app.services.sale_builder import resolve_sale_owner, to_sale_response

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])

ITEM_LABELS = {"en_almacen": "En almacén", "reservada": "Reservada", "vendida": "Vendida", "descartada": "Descartada"}


def _visible_owner_ids(db: Session, user: User) -> list[uuid.UUID]:
    return readable_user_ids(db, user)


def _item_query(db: Session, user: User):
    return (
        db.query(WarehouseItem)
        .options(joinedload(WarehouseItem.origin_sale).joinedload(Sale.owner))
        .filter(WarehouseItem.user_id.in_(_visible_owner_ids(db, user)))
    )


def _get_visible_item(db: Session, item_id: uuid.UUID, user: User) -> WarehouseItem:
    item = _item_query(db, user).filter(WarehouseItem.id == item_id).first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pieza no encontrada")
    return item


def _get_managed_item(db: Session, item_id: uuid.UUID, user: User) -> WarehouseItem:
    """Editar y descartar: solo el dueño de la pieza."""
    item = _get_visible_item(db, item_id, user)
    if is_watcher(user) or item.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el dueño de la pieza puede editarla o descartarla.")
    return item


def _active_sale_id(db: Session, item: WarehouseItem):
    row = (
        db.query(Sale.id)
        .filter(Sale.warehouse_item_id == item.id, Sale.status != STATUS_CANCELLED)
        .order_by(Sale.created_at.desc())
        .first()
    )
    return row[0] if row else None


def _to_response(db: Session, item: WarehouseItem, viewer: User) -> WarehouseItemResponse:
    origin = item.origin_sale
    return WarehouseItemResponse(
        id=item.id,
        name=item.name,
        owner_id=item.user_id,
        owner_username=origin.owner.username,
        origin_sale_id=item.origin_sale_id,
        origin_client_name=origin.client_name,
        origin_cancelled_at=origin.cancelled_at,
        entry_date=item.entry_date,
        cost=item.cost,
        price=item.price,
        status=item.status,
        discard_reason=item.discard_reason,
        discarded_at=item.discarded_at,
        notes=item.notes,
        can_manage=not is_watcher(viewer) and item.user_id == viewer.id,
        active_sale_id=_active_sale_id(db, item) if item.status != ITEM_IN_STOCK else None,
    )


@router.get("", response_model=list[WarehouseItemResponse])
def list_items(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status_filter: str | None = Query(default=None, alias="status"),
    owner_id: uuid.UUID | None = Query(default=None),
):
    """Por defecto: piezas En almacén y Reservadas. `status=todos` o una lista separada por comas."""
    query = _item_query(db, current_user)
    if status_filter != "todos":
        wanted = status_filter.split(",") if status_filter else [ITEM_IN_STOCK, ITEM_RESERVED]
        if any(s not in WAREHOUSE_ITEM_STATUSES for s in wanted):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Estado de pieza inválido.")
        query = query.filter(WarehouseItem.status.in_(wanted))
    if owner_id is not None:
        query = query.filter(WarehouseItem.user_id == owner_id)
    items = query.order_by(WarehouseItem.entry_date.desc(), WarehouseItem.created_at.desc()).all()
    return [_to_response(db, i, current_user) for i in items]


@router.patch("/{item_id}", response_model=WarehouseItemResponse)
def update_item(
    item_id: uuid.UUID,
    payload: WarehouseItemUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = _get_managed_item(db, item_id, current_user)
    if item.status not in (ITEM_IN_STOCK, ITEM_RESERVED):
        raise HTTPException(status.HTTP_409_CONFLICT, f"La pieza está {ITEM_LABELS[item.status]}: ya no se edita.")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("name") is not None:
        item.name = changes["name"]
    if changes.get("price") is not None:
        item.price = money(changes["price"])
    if "notes" in changes:
        item.notes = (changes["notes"] or "").strip() or None
    log_event(
        db,
        user_id=current_user.id,
        event_type="WAREHOUSE_ITEM_UPDATED",
        entity_type="warehouse_item",
        entity_id=item.id,
        details={"changes": {k: str(v) for k, v in changes.items()}},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _to_response(db, _get_visible_item(db, item.id, current_user), current_user)


@router.post("/{item_id}/discard", response_model=WarehouseItemResponse)
def discard_item(
    item_id: uuid.UUID,
    payload: WarehouseDiscardRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Descartar: el costo de la pieza pasa a contar como pérdida (en la fecha del descarte)."""
    item = _get_managed_item(db, item_id, current_user)
    if item.status == ITEM_RESERVED:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "La pieza está reservada por un pedido: cancela o elimina ese pedido primero."
        )
    if item.status != ITEM_IN_STOCK:
        raise HTTPException(status.HTTP_409_CONFLICT, f"La pieza ya está {ITEM_LABELS[item.status]}.")
    item.status = ITEM_DISCARDED
    item.discard_reason = payload.reason
    item.discarded_at = utcnow()
    if payload.note:
        item.notes = f"{item.notes}\n{payload.note}".strip() if item.notes else payload.note.strip()
    log_event(
        db,
        user_id=current_user.id,
        event_type="WAREHOUSE_ITEM_DISCARDED",
        entity_type="warehouse_item",
        entity_id=item.id,
        details={"name": item.name, "cost": str(item.cost), "reason": payload.reason, "note": payload.note},
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return _to_response(db, _get_visible_item(db, item.id, current_user), current_user)


def _cost_breakdown_from_origin(item: WarehouseItem, origin: Sale) -> dict:
    """Desglose del costo de la pieza a partir del pedido original (lo que quedó consumido
    al cancelar). Así el Dashboard reparte ese costo como siempre (material, luz, etc.)."""
    parts = {
        "material_cost": origin.material_cost if not origin.materials_returned else Decimal(0),
        "supplies_cost": origin.supplies_cost if not origin.supplies_returned else Decimal(0),
        "depreciation_cost": origin.depreciation_cost if not origin.hours_returned else Decimal(0),
        "energy_cost": origin.energy_cost if not origin.hours_returned else Decimal(0),
        "postprocess_cost": origin.postprocess_cost,
    }
    # Por si hubiera algún centavo de diferencia por redondeo, se ajusta en material.
    parts["material_cost"] += item.cost - sum(parts.values())
    return parts


@router.post("/{item_id}/sell", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
def sell_item(
    item_id: uuid.UUID,
    payload: WarehouseSellRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Crea un pedido nuevo vinculado a la pieza, que nace en Lista. No descuenta material
    ni suma horas (eso ya ocurrió); su costo es el de la pieza. La pieza queda Reservada y
    pasa a Vendida cuando el pedido se entrega."""
    item = _get_visible_item(db, item_id, current_user)
    if item.status != ITEM_IN_STOCK:
        raise HTTPException(status.HTTP_409_CONFLICT, f"La pieza está {ITEM_LABELS[item.status]}: no se puede vender.")
    # El pedido es del dueño de la pieza; si lo registra un observador, debe tenerlo asignado.
    owner_id = resolve_sale_owner(db, current_user, item.user_id)
    origin = item.origin_sale
    if payload.payment_method == GIFT_PAYMENT_METHOD:
        price = Decimal(0)  # regalo: sin cobro, el costo de la pieza queda igual
    else:
        price = money(payload.price if payload.price is not None else item.price)
    today = date.today()

    sale = Sale(
        user_id=owner_id,
        created_by_user_id=current_user.id,
        sale_date=payload.sale_date or today,
        client_name=payload.client_name or item.name,
        buyer_name=payload.buyer_name,
        printer_id=origin.printer_id,
        grams_used=0,
        print_hours=0,
        postprocess_hours=0,
        base_price=price,
        iva_percent=0,
        iva_amount=0,
        total_price=price,
        shipping_cost=0,
        total_cost=item.cost,
        profit=money(price - item.cost),
        margin_percent=calculate_margin_percent(price, item.cost),
        payment_method=payload.payment_method,
        notes=payload.notes,
        status=STATUS_READY,
        promised_delivery_date=payload.promised_delivery_date,
        delivered_date=None,
        warehouse_item_id=item.id,
        # Nada que devolver si se elimina o cancela: el material era del pedido original.
        materials_returned=True,
        supplies_returned=True,
        hours_returned=True,
        **_cost_breakdown_from_origin(item, origin),
    )
    db.add(sale)
    db.flush()
    record_status(db, sale, STATUS_READY, current_user, f"Venta de la pieza del Almacén «{item.name}»")
    item.status = ITEM_RESERVED

    ip = request.client.host if request.client else None
    log_event(
        db,
        user_id=current_user.id,
        event_type="SALE_CREATED",
        entity_type="sale",
        entity_id=sale.id,
        details={"source": "warehouse", "warehouse_item_id": str(item.id), "client_name": sale.client_name,
                 "price": str(price), "owner_id": str(owner_id), "status": sale.status},
        ip_address=ip,
    )
    log_event(
        db,
        user_id=current_user.id,
        event_type="WAREHOUSE_ITEM_RESERVED",
        entity_type="warehouse_item",
        entity_id=item.id,
        details={"sale_id": str(sale.id), "price": str(price)},
        ip_address=ip,
    )
    db.commit()
    db.refresh(sale)
    background_tasks.add_task(announce_order, sale.id)
    return to_sale_response(sale, viewer=current_user, include_history=True)
