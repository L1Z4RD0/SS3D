"""Ciclo de vida de los pedidos: estados, transiciones permitidas e historial."""
from datetime import date

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import utcnow
from app.models.sale import (
    STATUS_CANCELLED,
    STATUS_DELIVERED,
    STATUS_IN_PRODUCTION,
    STATUS_PENDING,
    STATUS_READY,
    Sale,
)
from app.models.sale_status_history import SaleStatusHistory
from app.models.user import User
from app.schemas.sale import UNPAID_PAYMENT_METHOD
from app.models.warehouse_item import ITEM_RESERVED, ITEM_SOLD, WarehouseItem

STATUS_LABELS = {
    STATUS_PENDING: "Pendiente",
    STATUS_IN_PRODUCTION: "En producción",
    STATUS_READY: "Lista",
    STATUS_DELIVERED: "Entregada",
    STATUS_CANCELLED: "Cancelado",
}
# Flujo normal y su reverso (retroceder un paso no toca el inventario).
NEXT_STATUS = {STATUS_PENDING: STATUS_IN_PRODUCTION, STATUS_IN_PRODUCTION: STATUS_READY, STATUS_READY: STATUS_DELIVERED}
PREV_STATUS = {STATUS_IN_PRODUCTION: STATUS_PENDING, STATUS_READY: STATUS_IN_PRODUCTION}
FINAL_STATUSES = (STATUS_DELIVERED, STATUS_CANCELLED)
OPEN_STATUSES = (STATUS_PENDING, STATUS_IN_PRODUCTION, STATUS_READY)
# En estos estados la pieza ya se está fabricando: no se tocan materiales ni horas.
LOCKED_PRODUCTION_STATUSES = (STATUS_IN_PRODUCTION, STATUS_READY)


def record_status(
    db: Session, sale: Sale, new_status: str, user: User | None, note: str | None = None, at=None
) -> None:
    """Deja constancia de un paso del pedido: qué estado, cuándo y quién lo movió."""
    db.add(
        SaleStatusHistory(
            sale_id=sale.id,
            status=new_status,
            changed_at=at or utcnow(),
            changed_by_user_id=user.id if user is not None else None,
            note=note,
        )
    )


def start_as_pending(sale: Sale, promised_delivery_date: date | None) -> None:
    """Un pedido nuevo nace Pendiente, con su fecha de entrega comprometida (por defecto,
    la fecha del pedido). No cuenta como ingreso hasta que se entregue."""
    sale.status = STATUS_PENDING
    sale.promised_delivery_date = promised_delivery_date or sale.sale_date
    sale.delivered_date = None


PAYMENT_LABELS = {"efectivo": "efectivo", "transferencia": "transferencia", "debito": "débito", "credito": "crédito"}
MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
             "noviembre", "diciembre")


def long_date(d: date) -> str:
    """12 de noviembre (con el año solo si no es el actual)."""
    text = f"{d.day} de {MONTHS_ES[d.month - 1]}"
    return text if d.year == date.today().year else f"{text} de {d.year}"


def _settle_on_delivery(sale: Sale, payment_method: str | None, due_date: date | None, today: date) -> str | None:
    """Entregar un pedido "Por cobrar" obliga a decir cómo pagó o, si aún no paga, hasta
    cuándo tiene plazo. Valida antes de tocar nada; devuelve la nota para el historial."""
    if sale.payment_method != UNPAID_PAYMENT_METHOD:
        return None
    if payment_method:
        return f"Pagó al entregar: {PAYMENT_LABELS.get(payment_method, payment_method)}"
    if due_date is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El pedido está Por cobrar: indica cómo pagó o, si aún no paga, la fecha máxima de pago.",
        )
    if due_date < today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La fecha máxima de pago no puede ser anterior a hoy.")
    return f"Entregado sin pagar: cobrar el {long_date(due_date)}"


def change_status(
    db: Session,
    sale: Sale,
    target: str,
    user: User,
    *,
    skip_confirmed: bool,
    today: date,
    payment_method: str | None = None,
    payment_due_date: date | None = None,
) -> list[str]:
    """Aplica una transición validada. Devuelve los estados recorridos (más de uno si se
    salta directo a Entregada: los pasos intermedios quedan registrados con la misma hora)."""
    current = sale.status
    # Corrección: un pedido marcado Entregado por error vuelve a Lista. Deja de contar como
    # ingreso (todo se calcula solo con los Entregados) y vuelve a contar si se entrega otra vez.
    undo_delivery = current == STATUS_DELIVERED and target == STATUS_READY
    if current in FINAL_STATUSES and not undo_delivery:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"El pedido está {STATUS_LABELS[current]}: es un estado final y no se puede cambiar."
        )
    if target == STATUS_CANCELLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Para cancelar un pedido usa la opción Cancelar.")
    if target == current:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El pedido ya está {STATUS_LABELS[current]}.")

    if undo_delivery:
        path, note = [target], "Corrección: vuelve de Entregada a Lista (deja de contar como ingreso)"
    elif target == NEXT_STATUS.get(current):
        path, note = [target], None
    elif target == PREV_STATUS.get(current):
        if sale.warehouse_item_id is not None:
            # Un pedido de una pieza del Almacén nace Lista: la pieza ya existe.
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Un pedido de una pieza del Almacén no puede volver a producción."
            )
        path, note = [target], "Retroceso de estado"
    elif target == STATUS_DELIVERED and current in (STATUS_PENDING, STATUS_IN_PRODUCTION):
        if not skip_confirmed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Pasar directo a Entregada salta pasos: confírmalo para registrar los pasos intermedios.",
            )
        path = [STATUS_IN_PRODUCTION, STATUS_READY, STATUS_DELIVERED] if current == STATUS_PENDING else [
            STATUS_READY,
            STATUS_DELIVERED,
        ]
        note = "Entrega directa (pasos intermedios registrados automáticamente)"
    else:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"No se puede pasar de {STATUS_LABELS[current]} a {STATUS_LABELS.get(target, target)}.",
        )

    payment_note = _settle_on_delivery(sale, payment_method, payment_due_date, today) if target == STATUS_DELIVERED else None

    at = utcnow()
    for step in path:
        step_note = note
        if step == STATUS_DELIVERED and payment_note:
            step_note = f"{note}. {payment_note}" if note else payment_note
        record_status(db, sale, step, user, step_note, at=at)
    sale.status = target
    if undo_delivery:
        sale.delivered_date = None
        # Si era "Por cobrar" y se cobró, vuelve a "Por cobrar": el cobro se registra de
        # nuevo al entregarlo otra vez.
        if sale.paid_date is not None:
            sale.payment_method = UNPAID_PAYMENT_METHOD
        sale.paid_date = None
        sale.payment_due_date = None
        if sale.warehouse_item_id is not None:
            # La pieza del Almacén vuelve a estar Reservada para este pedido.
            item = db.get(WarehouseItem, sale.warehouse_item_id)
            if item is not None and item.status == ITEM_SOLD:
                item.status = ITEM_RESERVED
    if target == STATUS_DELIVERED:
        sale.delivered_date = today
        if payment_note:
            if payment_method:
                sale.payment_method = payment_method
                sale.paid_date = today
                sale.payment_due_date = None
            else:
                sale.payment_due_date = payment_due_date
        if sale.warehouse_item_id is not None:
            # La pieza del Almacén se entregó: pasa de Reservada a Vendida.
            item = db.get(WarehouseItem, sale.warehouse_item_id)
            if item is not None:
                item.status = ITEM_SOLD
    return path
