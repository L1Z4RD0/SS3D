from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import UUIDMixin


class SaleSupply(UUIDMixin, Base):
    __tablename__ = "sale_supplies"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    supply_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("supplies.id", ondelete="RESTRICT"), nullable=False
    )
    quantity_used: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    unit_cost_snapshot: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # Unidades que se usaron sin tener stock ("fiadas": el insumo quedó en negativo). Se
    # costean provisionalmente al último precio y se recalculan al precio real cuando se
    # registra la compra (Reponer). 0 = el costo de esta línea es definitivo.
    pending_qty: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0, server_default="0")
    # Diferencia (precio real − provisional) de las unidades fiadas ya saldadas. El costo de
    # la línea es quantity_used × unit_cost_snapshot + cost_adjustment: el precio provisional
    # no se toca, así una reposición parcial posterior sigue calculando desde él.
    cost_adjustment: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    sale: Mapped["Sale"] = relationship(back_populates="supplies_used")
    supply: Mapped["Supply"] = relationship()
