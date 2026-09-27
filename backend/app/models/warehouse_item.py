from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

ITEM_IN_STOCK = "en_almacen"
ITEM_RESERVED = "reservada"
ITEM_SOLD = "vendida"
ITEM_DISCARDED = "descartada"
WAREHOUSE_ITEM_STATUSES = (ITEM_IN_STOCK, ITEM_RESERVED, ITEM_SOLD, ITEM_DISCARDED)
DISCARD_REASONS = ("regalada", "danada", "desechada", "otro")


class WarehouseItem(UUIDMixin, TimestampMixin, Base):
    """Pieza de un pedido cancelado que sigue en poder del negocio."""

    __tablename__ = "warehouse_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('en_almacen', 'reservada', 'vendida', 'descartada')", name="ck_warehouse_items_status"
        ),
    )

    # Dueño de la pieza: el dueño del inventario con que se fabricó.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    origin_sale_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Costo heredado del pedido original (sin envío). Se mantiene como "valor en Almacén"
    # hasta que la pieza se vende (pasa a ser el costo de esa venta) o se descarta (pérdida).
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=ITEM_IN_STOCK, index=True)
    discard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    discarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    origin_sale: Mapped["Sale"] = relationship(foreign_keys=[origin_sale_id])
