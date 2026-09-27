from sqlalchemy.orm import Session

from app.models.sale import STATUS_DELIVERED, Sale
from app.models.sale_status_history import SaleStatusHistory
from app.models.user import User


def record_status(db: Session, sale: Sale, status: str, user: User | None, note: str | None = None) -> None:
    """Deja constancia de un paso del pedido: qué estado, cuándo y quién lo movió."""
    db.add(
        SaleStatusHistory(
            sale_id=sale.id,
            status=status,
            changed_by_user_id=user.id if user is not None else None,
            note=note,
        )
    )


def start_as_delivered(sale: Sale) -> None:
    """Fase 1 (antes de los estados en pantalla): una venta nueva queda como hasta hoy,
    Entregada en su fecha de venta, igual que las ventas migradas. Así el Dashboard y el
    Historial siguen dando exactamente lo mismo."""
    sale.status = STATUS_DELIVERED
    sale.promised_delivery_date = sale.sale_date
    sale.delivered_date = sale.sale_date


def sync_legacy_dates(sale: Sale) -> None:
    """Fase 1: si se corrige la fecha de venta de una venta entregada, sus fechas de
    entrega la siguen (hoy son la misma fecha)."""
    if sale.status == STATUS_DELIVERED:
        sale.promised_delivery_date = sale.sale_date
        sale.delivered_date = sale.sale_date
