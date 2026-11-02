from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin, utcnow


class CashBoxClosing(UUIDMixin, TimestampMixin, Base):
    """Lo que de verdad quedó en la Caja de la Empresa al cerrar un mes (contado a mano),
    con la explicación. Es el saldo con que arranca el mes siguiente en el Reparto (beta)."""

    __tablename__ = "cash_box_closings"

    month: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # AAAA-MM
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CashBoxWithdrawal(UUIDMixin, Base):
    """Plata que se sacó de la Caja y para qué se usó. Solo baja el saldo de la Caja: no
    cambia el Reparto (para una compra que se reparte entre todos están los Gastos)."""

    __tablename__ = "cash_box_withdrawals"

    withdrawal_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    concept: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
