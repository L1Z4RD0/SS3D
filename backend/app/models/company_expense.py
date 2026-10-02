from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDMixin, utcnow


class CompanyExpense(UUIDMixin, Base):
    """Compra o gasto de la Empresa (bolsas, argollas, filamento...). Solo lo usa el módulo
    beta de Reparto: no afecta inventario, ventas ni el Dashboard."""

    __tablename__ = "company_expenses"

    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    concept: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Quién lo pagó: "Caja" o el nombre de un socio (a quien se le devuelve).
    paid_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
