from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin, utcnow


class SalePlate(UUIDMixin, Base):
    """Plancha adicional de un pedido (la principal son la impresora, horas y filamentos
    de la propia venta). Sirve para un mismo producto impreso en varias planchas (ej. el
    portallaveros en una y los llaveros en otra, incluso en otra impresora) y para las
    reimpresiones por fallo, que suman costo sin cambiar el precio."""

    __tablename__ = "sale_plates"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    printer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("printers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    print_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    is_reprint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Costos de esta plancha al momento de registrarla (ya incluidos en los totales de la venta).
    material_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    depreciation_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    energy_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="plates")
    printer: Mapped["Printer"] = relationship()
    filaments_used: Mapped[list["SalePlateFilament"]] = relationship(
        back_populates="plate", cascade="all, delete-orphan"
    )

    @property
    def total_cost(self) -> Decimal:
        return self.material_cost + self.depreciation_cost + self.energy_cost


class SalePlateFilament(UUIDMixin, Base):
    __tablename__ = "sale_plate_filaments"

    plate_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sale_plates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filament_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("filaments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    grams_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    material_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    plate: Mapped["SalePlate"] = relationship(back_populates="filaments_used")
    filament: Mapped["Filament"] = relationship()
