"""Cancelación de pedidos: qué se devuelve al inventario, qué queda como pérdida y qué
pieza pasa al Almacén.

Reglas (acordadas con el negocio):
- Pendiente: se devuelve todo (gramos, insumos y horas). Sin pérdida.
- En producción: el filamento queda consumido; los insumos se DEVUELVEN (normalmente aún
  no se ponen); las horas según la respuesta del usuario. Si la pieza quedó utilizable
  va al Almacén; si no, su costo es pérdida.
- Lista: filamento e insumos quedan consumidos; horas según la respuesta. La pieza va al
  Almacén o se descarta con motivo (queda registrada como pieza Descartada).
- Costo de la pieza (y de la pérdida) = material + insumos consumidos + postprocesado +
  depreciación y energía solo si se dejan registradas las horas. Nunca el envío.
- Un pedido que vendía una pieza del Almacén: la pieza vuelve al Almacén, sin preguntas.
"""
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.sale import (
    STATUS_CANCELLED,
    STATUS_IN_PRODUCTION,
    STATUS_PENDING,
    STATUS_READY,
    Sale,
)
from app.models.user import User
from app.models.warehouse_item import (
    DISCARD_REASONS,
    ITEM_DISCARDED,
    ITEM_IN_STOCK,
    ITEM_RESERVED,
    ITEM_SOLD,
    WarehouseItem,
)
from app.services.calculator import money
from app.services.inventory import restore_filament, restore_supply
from app.services.sale_plates import return_plates_hours, return_plates_materials
from app.services.order_status import STATUS_LABELS, record_status

OUTCOME_WAREHOUSE = "almacen"
OUTCOME_DISCARD = "descartar"
OUTCOME_UNUSABLE = "inutilizable"


def _return_materials(sale: Sale) -> None:
    if not sale.materials_returned:
        for sf in sale.filaments_used:
            restore_filament(sf.filament, sf.grams_used)
        return_plates_materials(sale)
        sale.materials_returned = True


def _return_supplies(sale: Sale) -> None:
    if not sale.supplies_returned:
        for ss in sale.supplies_used:
            restore_supply(ss.supply, ss.quantity_used)
            ss.pending_qty = 0  # lo fiado se devolvió: ya no hay nada que recalcular
        sale.supplies_returned = True


def _return_hours(sale: Sale) -> None:
    if not sale.hours_returned:
        sale.printer.hours_used -= sale.print_hours
        return_plates_hours(sale)
        sale.hours_returned = True


def undo_remaining_consumption(sale: Sale) -> None:
    """Devuelve lo que el pedido todavía tiene consumido. Lo usa Eliminar: en un pedido
    cancelado, lo que ya se devolvió al cancelar no se vuelve a devolver."""
    _return_materials(sale)
    _return_supplies(sale)
    _return_hours(sale)


def consumed_cost(sale: Sale) -> Decimal:
    """Costo de lo que quedó consumido tras cancelar (sin envío, que nunca se hizo)."""
    cost = sale.postprocess_cost
    if not sale.materials_returned:
        cost += sale.material_cost
    if not sale.supplies_returned:
        cost += sale.supplies_cost
    if not sale.hours_returned:
        cost += sale.depreciation_cost + sale.energy_cost
    return money(cost)


def cancel_order(
    db: Session,
    sale: Sale,
    user: User,
    *,
    keep_hours: bool,
    piece_outcome: str | None,
    discard_reason: str | None,
    reason: str | None,
    today: date,
) -> WarehouseItem | None:
    current = sale.status
    if current not in (STATUS_PENDING, STATUS_IN_PRODUCTION, STATUS_READY):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"El pedido está {STATUS_LABELS[current]}: es un estado final y no se puede cancelar."
        )

    piece = None
    notes = []

    if sale.warehouse_item_id is not None:
        # Venta de una pieza del Almacén: nada que devolver (el material ya se usó en el
        # pedido original); la pieza vuelve a estar disponible.
        item = db.get(WarehouseItem, sale.warehouse_item_id)
        if item is not None and item.status in (ITEM_RESERVED, ITEM_SOLD):
            item.status = ITEM_IN_STOCK
        sale.materials_returned = sale.supplies_returned = sale.hours_returned = True
        notes.append("La pieza vuelve al Almacén")
    elif current == STATUS_PENDING:
        undo_remaining_consumption(sale)
        notes.append("Se devolvieron filamento, insumos y horas")
    else:
        if current == STATUS_IN_PRODUCTION:
            if piece_outcome not in (OUTCOME_WAREHOUSE, OUTCOME_UNUSABLE):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica si la pieza quedó utilizable.")
            _return_supplies(sale)
            notes.append("Insumos devueltos")
        else:  # Lista
            if piece_outcome not in (OUTCOME_WAREHOUSE, OUTCOME_DISCARD):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica si la pieza va al Almacén o se descarta.")
            if piece_outcome == OUTCOME_DISCARD and discard_reason not in DISCARD_REASONS:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Indica el motivo del descarte.")
        if keep_hours:
            notes.append("Horas de impresión registradas")
        else:
            _return_hours(sale)
            notes.append("Horas de impresión devueltas a la impresora")

        cost = consumed_cost(sale)
        if piece_outcome in (OUTCOME_WAREHOUSE, OUTCOME_DISCARD):
            piece = WarehouseItem(
                user_id=sale.user_id,
                origin_sale_id=sale.id,
                name=sale.client_name,
                entry_date=today,
                cost=cost,
                price=sale.total_price,
                status=ITEM_IN_STOCK,
            )
            if piece_outcome == OUTCOME_DISCARD:
                piece.status = ITEM_DISCARDED
                piece.discard_reason = discard_reason
                piece.discarded_at = utcnow()
                notes.append("Pieza descartada")
            else:
                notes.append("Pieza enviada al Almacén")
            db.add(piece)
        else:
            sale.loss_amount = cost
            notes.append("Pieza no utilizable: su costo queda como pérdida")

    sale.status = STATUS_CANCELLED
    sale.cancelled_at = utcnow()
    sale.cancel_reason = (reason or "").strip() or None
    note = ". ".join(notes)
    if sale.cancel_reason:
        note = f"{note}. Motivo: {sale.cancel_reason}"
    record_status(db, sale, STATUS_CANCELLED, user, note)
    return piece


def check_can_delete(db: Session, sale: Sale) -> list[WarehouseItem]:
    """Eliminar un pedido cancelado con pieza en el Almacén: si la pieza sigue ahí (o se
    descartó al cancelar) se elimina junto con el pedido; si está reservada o vendida,
    primero hay que resolver esa venta."""
    items = db.query(WarehouseItem).filter(WarehouseItem.origin_sale_id == sale.id).all()
    if any(i.status in (ITEM_RESERVED, ITEM_SOLD) for i in items):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "La pieza de este pedido está reservada o vendida en el Almacén. Resuelve primero esa venta.",
        )
    return items
