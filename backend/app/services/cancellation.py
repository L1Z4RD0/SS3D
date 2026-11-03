"""Cancelación de pedidos: qué se devuelve al inventario, qué queda como pérdida y qué
pieza pasa al Almacén.

Reglas (acordadas con el negocio):
- Pendiente: se devuelve todo (gramos, insumos y horas). Sin pérdida.
- En producción: el filamento queda consumido; los insumos se DEVUELVEN (normalmente aún
  no se ponen); las horas según la respuesta del usuario. Si la pieza quedó utilizable
  va al Almacén; si no, su costo es pérdida.
- Lista: filamento e insumos quedan consumidos; horas según la respuesta. La pieza va al
  Almacén o se descarta con motivo.
- Costo de la pieza (y de la pérdida) = material + insumos consumidos + postprocesado +
  depreciación y energía solo si se dejan registradas las horas. Nunca el envío.
- Un pedido que vendía una pieza del Almacén: la pieza vuelve al Almacén, sin preguntas.

Pieza dañada (desde el 2026-11-03): En producción "no sirve", o Lista "descartarla". Se
indica qué % de la pieza se alcanzó a imprimir (1 a 100), cuántas horas se usaron y si se
hizo el postprocesado. Solo eso queda consumido: el filamento y las horas que no se usaron
vuelven al inventario y a la impresora. La pérdida queda SIEMPRE en el pedido (loss_amount)
y el Reparto la devuelve a cada dueño de recurso en el mes de la cancelación.
"""
from datetime import date, timezone
from zoneinfo import ZoneInfo
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
from app.services.cost_allocation import consumed_total, consumption_factors, planned_print_hours
from app.services.inventory import consume_filament, restore_filament, restore_supply
from app.services.order_status import STATUS_LABELS, record_status

OUTCOME_WAREHOUSE = "almacen"
OUTCOME_DISCARD = "descartar"
OUTCOME_UNUSABLE = "inutilizable"
DISCARD_LABELS = {"regalada": "regalada", "danada": "dañada", "desechada": "desechada", "otro": "otro motivo"}


def _apply_partial_print(
    sale: Sale,
    printed_percent: Decimal | None,
    print_hours_used: Decimal | None,
    postprocess_done: bool,
    keep_hours: bool,
) -> None:
    """Guarda cuánto se alcanzó a imprimir y devuelve al inventario lo que no se usó."""
    planned = planned_print_hours(sale)
    if printed_percent is None:
        # Versión anterior de la app (sin la pregunta del %): todo impreso, salvo que haya
        # pedido devolver las horas, que significa que no se imprimió nada.
        printed_percent = Decimal(100) if keep_hours else Decimal(0)
        print_hours_used = planned if keep_hours else Decimal(0)
    printed_percent = Decimal(printed_percent)
    if not Decimal(0) <= printed_percent <= Decimal(100):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El % impreso debe estar entre 1 y 100.")
    if print_hours_used is None:
        print_hours_used = money(planned * printed_percent / 100)
    print_hours_used = Decimal(print_hours_used)
    if print_hours_used < 0 or print_hours_used > planned:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Las horas usadas deben estar entre 0 y las {num(planned)} h del pedido.",
        )
    sale.cancel_printed_percent = printed_percent
    sale.cancel_print_hours = print_hours_used
    sale.cancel_postprocess_done = bool(postprocess_done)
    factors = consumption_factors(sale)
    _shift_materials(sale, 1 - factors.material)
    _shift_hours(sale, 1 - factors.machine)


def num(value: Decimal) -> str:
    """Número sin ceros de más, con coma decimal (50 → "50", 1.80 → "1,8")."""
    text = format(Decimal(value).normalize(), "f")
    return text.replace(".", ",")


def _partial_note(sale: Sale) -> str:
    post = "con postprocesado" if sale.cancel_postprocess_done else "sin postprocesado"
    return (f"{num(sale.cancel_printed_percent)} % impreso, {num(sale.cancel_print_hours)} h de impresión, {post}. "
            f"Pérdida ${sale.loss_amount:,.0f}".replace(",", "."))


def _shift_materials(sale: Sale, fraction: Decimal) -> None:
    """Devuelve al inventario esa fracción de los gramos del pedido (todas sus planchas). Si
    la fracción es negativa, en cambio descuenta (al corregir una pérdida hacia arriba)."""
    lines = [*sale.filaments_used, *(pf for p in sale.plates for pf in p.filaments_used)]
    for line in lines:
        grams = money(line.grams_used * abs(fraction))
        if fraction > 0:
            restore_filament(line.filament, grams)
        elif fraction < 0:
            consume_filament(line.filament, grams)


def _shift_hours(sale: Sale, fraction: Decimal) -> None:
    """Devuelve a cada impresora esa fracción de las horas del pedido (negativa: las suma)."""
    sale.printer.hours_used -= money(sale.print_hours * fraction)
    for plate in sale.plates:
        plate.printer.hours_used -= money(plate.print_hours * fraction)


def _return_materials(sale: Sale) -> None:
    if not sale.materials_returned:
        # Lo que sigue consumido: todo, o solo el % impreso si la pieza se dañó a medio camino.
        _shift_materials(sale, consumption_factors(sale).material)
        sale.materials_returned = True


def _return_supplies(sale: Sale) -> None:
    if not sale.supplies_returned:
        for ss in sale.supplies_used:
            restore_supply(ss.supply, ss.quantity_used)
            ss.pending_qty = 0  # lo fiado se devolvió: ya no hay nada que recalcular
        sale.supplies_returned = True


def _return_hours(sale: Sale) -> None:
    if not sale.hours_returned:
        _shift_hours(sale, consumption_factors(sale).machine)
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
    printed_percent: Decimal | None = None,
    print_hours_used: Decimal | None = None,
    postprocess_done: bool = False,
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
        damaged = piece_outcome in (OUTCOME_UNUSABLE, OUTCOME_DISCARD)
        if damaged:
            # La pieza no sirve: solo queda consumido lo que se alcanzó a imprimir.
            _apply_partial_print(sale, printed_percent, print_hours_used, postprocess_done, keep_hours)
            if piece_outcome == OUTCOME_DISCARD:
                sale.cancel_discard_reason = discard_reason
                notes.append(f"Pieza descartada ({DISCARD_LABELS.get(discard_reason, discard_reason)})")
            else:
                notes.append("Pieza no utilizable")
            sale.loss_amount = consumed_total(sale)
            notes.append(_partial_note(sale))
        else:
            if keep_hours:
                notes.append("Horas de impresión registradas")
            else:
                _return_hours(sale)
                notes.append("Horas de impresión devueltas a la impresora")
            piece = WarehouseItem(
                user_id=sale.user_id,
                origin_sale_id=sale.id,
                name=sale.client_name,
                entry_date=today,
                cost=consumed_cost(sale),
                price=sale.total_price,
                status=ITEM_IN_STOCK,
            )
            notes.append("Pieza enviada al Almacén")
            db.add(piece)

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


# ---------------------------------------------------------------------------
# Corregir la pérdida de un pedido cancelado (mismo mes)
# ---------------------------------------------------------------------------


LOCAL_TZ = ZoneInfo("America/Santiago")


def cancelled_local_date(sale: Sale) -> date:
    """Día (hora de Chile) en que se canceló el pedido."""
    at = sale.cancelled_at
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return at.astimezone(LOCAL_TZ).date()


def loss_is_editable(sale: Sale, today: date) -> bool:
    """Se puede corregir el % impreso de un cancelado con la pieza dañada, solo durante el
    mes en que se canceló (los meses anteriores no se tocan, para no descuadrar el Reparto).
    También los cancelados antes de esta función (ej. una pieza descartada al cancelar)."""
    if sale.status != STATUS_CANCELLED or sale.warehouse_item_id is not None or sale.cancelled_at is None:
        return False
    cancelled = cancelled_local_date(sale)
    if (cancelled.year, cancelled.month) != (today.year, today.month):
        return False
    if sale.cancel_printed_percent is not None:
        return True
    pieces = sale.origin_pieces
    if pieces:
        # Antes, descartar al cancelar dejaba la pérdida en una pieza "Descartada".
        return all(p.status == ITEM_DISCARDED for p in pieces)
    return sale.loss_amount > 0


def edit_cancellation_loss(
    db: Session,
    sale: Sale,
    user: User,
    *,
    printed_percent: Decimal,
    print_hours_used: Decimal | None,
    postprocess_done: bool,
    today: date,
) -> None:
    if not loss_is_editable(sale, today):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Solo se puede corregir la pérdida de un pedido cancelado con la pieza dañada, durante el mes en que se canceló.",
        )
    before = consumption_factors(sale)
    old_loss = sale.loss_amount
    # Un cancelado anterior con la pérdida en una pieza "Descartada": la pérdida pasa al pedido.
    for piece in list(sale.origin_pieces):
        if piece.status == ITEM_DISCARDED:
            old_loss = old_loss or piece.cost
            if not sale.cancel_discard_reason:
                sale.cancel_discard_reason = piece.discard_reason
            db.delete(piece)

    planned = planned_print_hours(sale)
    printed_percent = Decimal(printed_percent)
    if not Decimal(1) <= printed_percent <= Decimal(100):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El % impreso debe estar entre 1 y 100.")
    if print_hours_used is None:
        print_hours_used = money(planned * printed_percent / 100)
    print_hours_used = Decimal(print_hours_used)
    if print_hours_used < 0 or print_hours_used > planned:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Las horas usadas deben estar entre 0 y las {num(planned)} h del pedido."
        )
    sale.cancel_printed_percent = printed_percent
    sale.cancel_print_hours = print_hours_used
    sale.cancel_postprocess_done = bool(postprocess_done)
    sale.materials_returned = sale.hours_returned = False
    after = consumption_factors(sale)
    # Lo que se usó de más vuelve al inventario; si ahora se usó más, se descuenta.
    _shift_materials(sale, before.material - after.material)
    _shift_hours(sale, before.machine - after.machine)
    sale.loss_amount = consumed_total(sale)
    record_status(
        db, sale, STATUS_CANCELLED, user,
        f"Pérdida corregida: {_partial_note(sale)} (antes ${old_loss:,.0f})".replace(",", "."),
    )
