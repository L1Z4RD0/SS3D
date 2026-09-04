from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin


class SaleFilament(UUIDMixin, Base):
    __tablename__ = "sale_filaments"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("filaments.id", ondelete="RESTRICT"), nullable=False
    )
    grams_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    material_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="filaments_used")
    filament: Mapped["Filament"] = relationship()
