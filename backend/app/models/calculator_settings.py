from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import UUIDMixin, utcnow

DEFAULT_MARGIN_SCENARIOS = [60, 80, 100, 120, 140, 160, 180, 200]


class CalculatorSettings(UUIDMixin, Base):
    __tablename__ = "calculator_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    electricity_rate: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    labor_rate_per_hour: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    iva_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=19)
    margin_scenarios: Mapped[list] = mapped_column(JSONB, nullable=False, default=list(DEFAULT_MARGIN_SCENARIOS))
    default_packaging_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
