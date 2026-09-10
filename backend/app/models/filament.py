from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Filament(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "filaments"
    # NULLs don't conflict with each other in Postgres, so filaments without
    # an sku are unaffected — only non-null skus are enforced unique per user.
    __table_args__ = (UniqueConstraint("user_id", "sku", name="uq_filaments_user_sku"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brand: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(Text, nullable=False)
    sku: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    spool_weight_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=1000)
    initial_stock_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    used_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    available_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    min_alert_g: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    spool_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
