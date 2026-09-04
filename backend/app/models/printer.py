from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Printer(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "printers"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    purchase_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    lifetime_hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    power_kw: Mapped[Decimal] = mapped_column(Numeric(8, 3), nullable=False)
    hours_used: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    depreciation_cost_per_hour: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
