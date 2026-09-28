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
from app.models.warehouse_item import ITEM_SOLD, WarehouseItem

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


def change_status(
    db: Session, sale: Sale, target: str, user: User, *, skip_confirmed: bool, today: date
) -> list[str]:
    """Aplica una transición validada. Devuelve los estados recorridos (más de uno si se
    salta directo a Entregada: los pasos intermedios quedan registrados con la misma hora)."""
    current = sale.status
    if current in FINAL_STATUSES:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"El pedido está {STATUS_LABELS[current]}: es un estado final y no se puede cambiar."
        )
    if target == STATUS_CANCELLED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Para cancelar un pedido usa la opción Cancelar.")
    if target == current:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"El pedido ya está {STATUS_LABELS[current]}.")

    if target == NEXT_STATUS.get(current):
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

    at = utcnow()
    for step in path:
        record_status(db, sale, step, user, note, at=at)
    sale.status = target
    if target == STATUS_DELIVERED:
        sale.delivered_date = today
        if sale.warehouse_item_id is not None:
            # La pieza del Almacén se entregó: pasa de Reservada a Vendida.
            item = db.get(WarehouseItem, sale.warehouse_item_id)
            if item is not None:
                item.status = ITEM_SOLD
    return path
