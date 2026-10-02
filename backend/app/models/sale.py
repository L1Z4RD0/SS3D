from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin

# Ciclo de vida de un pedido. "Atrasado" no es un estado: es una marca visual cuando la
# fecha comprometida ya pasó y el pedido sigue abierto.
STATUS_PENDING = "pendiente"
STATUS_IN_PRODUCTION = "en_produccion"
STATUS_READY = "lista"
STATUS_DELIVERED = "entregada"
STATUS_CANCELLED = "cancelado"
ORDER_STATUSES = (STATUS_PENDING, STATUS_IN_PRODUCTION, STATUS_READY, STATUS_DELIVERED, STATUS_CANCELLED)


class Sale(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pendiente', 'en_produccion', 'lista', 'entregada', 'cancelado')", name="ck_sales_status"
        ),
    )

    # Dueño de la venta: el usuario cuyo inventario (impresora, filamentos, insumos) se usó.
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Quién la registró: el mismo dueño, o un observador (watcher) que vende con el
    # inventario del dueño. Se muestra siempre, por transparencia con el dueño.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
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

    # Riesgo de fallo cobrado en el precio: % del costo de producción y su monto. Es una
    # reserva dentro de la ganancia (no un costo). 0 en las ventas anteriores a este cambio.
    risk_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    risk_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    # Delivery: quién lo hizo y cuánto se le devuelve. Solo es un registro: no entra en el
    # precio, los costos ni la ganancia.
    delivery_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")

    payment_method: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---- Ciclo de vida del pedido ----
    # sale_date es la fecha del pedido. La comprometida la usa el Calendario; la real
    # (solo en Entregada) es la que usan el Dashboard y el Historial para contar ingresos.
    status: Mapped[str] = mapped_column(Text, nullable=False, default=STATUS_DELIVERED, index=True)
    promised_delivery_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    delivered_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # ---- Cancelación ----
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Qué se devolvió al cancelar, para que Eliminar un cancelado no devuelva dos veces.
    materials_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supplies_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hours_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Costo que la cancelación dejó como pérdida (0 si la pieza fue al Almacén).
    loss_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)

    # Si este pedido vende una pieza del Almacén, cuál es.
    warehouse_item_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("warehouse_items.id", ondelete="SET NULL"), nullable=True, index=True
    )

    supplies_used: Mapped[list["SaleSupply"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )
    filaments_used: Mapped[list["SaleFilament"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )
    printer: Mapped["Printer"] = relationship()
    filament: Mapped["Filament | None"] = relationship()
    owner: Mapped["User"] = relationship(foreign_keys=[user_id])
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    status_history: Mapped[list["SaleStatusHistory"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", order_by="SaleStatusHistory.changed_at"
    )
    # Planchas adicionales y reimpresiones (la principal es la impresora/horas/filamentos
    # de la venta).
    plates: Mapped[list["SalePlate"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", order_by="SalePlate.created_at"
    )
    # Pieza(s) que este pedido dejó en el Almacén al cancelarse (solo lectura).
    origin_pieces: Mapped[list["WarehouseItem"]] = relationship(
        primaryjoin="Sale.id == WarehouseItem.origin_sale_id", viewonly=True
    )
