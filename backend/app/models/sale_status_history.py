from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin, utcnow


class SaleStatusHistory(UUIDMixin, Base):
    """Cada paso del pedido: cuándo se creó y cómo fue avanzando, y quién lo movió."""

    __tablename__ = "sale_status_history"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Registros creados por la migración para las ventas que existían antes de los estados.
    is_migration: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    sale: Mapped["Sale"] = relationship(back_populates="status_history")
    changed_by: Mapped["User | None"] = relationship()
