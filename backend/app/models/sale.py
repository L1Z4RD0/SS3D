from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class Sale(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sales"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    client_name: Mapped[str] = mapped_column(Text, nullable=False)
    buyer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    printer_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("printers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    filament_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("filaments.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    grams_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    print_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    postprocess_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)

    base_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    iva_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    iva_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    material_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    depreciation_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    energy_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    postprocess_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    supplies_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    shipping_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    profit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    margin_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)

    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    supplies_used: Mapped[list["SaleSupply"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )
    printer: Mapped["Printer"] = relationship()
    filament: Mapped["Filament | None"] = relationship()
