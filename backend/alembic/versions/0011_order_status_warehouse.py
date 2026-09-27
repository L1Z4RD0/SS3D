"""order lifecycle (status, delivery dates, status history) + warehouse items

Revision ID: 0011_order_status
Revises: 0010_sale_created_by
Create Date: 2026-09-28

Todas las ventas existentes pasan a 'entregada', con fecha comprometida y fecha real
iguales a su sale_date, y un registro de historial marcado como migración. Así el
Dashboard y el Historial (que pasan a contar solo Entregadas por fecha real) dan
exactamente las mismas cifras que antes. No modifica ningún monto.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_order_status"
down_revision = "0010_sale_created_by"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # ---- 1. Columnas nuevas en sales (nullable primero, se rellenan, luego NOT NULL) ----
    op.add_column("sales", sa.Column("status", sa.Text(), nullable=True))
    op.add_column("sales", sa.Column("promised_delivery_date", sa.Date(), nullable=True))
    op.add_column("sales", sa.Column("delivered_date", sa.Date(), nullable=True))
    op.add_column("sales", sa.Column("cancel_reason", sa.Text(), nullable=True))
    op.add_column("sales", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    for col in ("materials_returned", "supplies_returned", "hours_returned"):
        op.add_column("sales", sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("sales", sa.Column("loss_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))

    op.execute(
        "UPDATE sales SET status = 'entregada', promised_delivery_date = sale_date, delivered_date = sale_date"
    )
    op.alter_column("sales", "status", nullable=False)
    op.alter_column("sales", "promised_delivery_date", nullable=False)
    op.create_check_constraint(
        "ck_sales_status", "sales", "status IN ('pendiente', 'en_produccion', 'lista', 'entregada', 'cancelado')"
    )
    op.create_index("ix_sales_status", "sales", ["status"])
    op.create_index("ix_sales_promised_delivery_date", "sales", ["promised_delivery_date"])
    op.create_index("ix_sales_delivered_date", "sales", ["delivered_date"])

    # ---- 2. Historial de estados ----
    op.create_table(
        "sale_status_history",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sale_id", UUID, sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_migration", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_sale_status_history_sale_id", "sale_status_history", ["sale_id"])
    # Un registro por venta existente: quedó "entregada" cuando se registró.
    op.execute(
        "INSERT INTO sale_status_history (id, sale_id, status, changed_at, changed_by_user_id, note, is_migration) "
        "SELECT gen_random_uuid(), id, 'entregada', created_at, created_by_user_id, "
        "'Venta registrada antes de los estados de pedido (migración)', true FROM sales"
    )

    # ---- 3. Almacén ----
    op.create_table(
        "warehouse_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("origin_sale_id", UUID, sa.ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="en_almacen"),
        sa.Column("discard_reason", sa.Text(), nullable=True),
        sa.Column("discarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('en_almacen', 'reservada', 'vendida', 'descartada')", name="ck_warehouse_items_status"
        ),
    )
    op.create_index("ix_warehouse_items_user_id", "warehouse_items", ["user_id"])
    op.create_index("ix_warehouse_items_origin_sale_id", "warehouse_items", ["origin_sale_id"])
    op.create_index("ix_warehouse_items_status", "warehouse_items", ["status"])

    # Pedido que vende una pieza del Almacén.
    op.add_column(
        "sales",
        sa.Column("warehouse_item_id", UUID, sa.ForeignKey("warehouse_items.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_sales_warehouse_item_id", "sales", ["warehouse_item_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_warehouse_item_id", table_name="sales")
    op.drop_column("sales", "warehouse_item_id")
    op.drop_table("warehouse_items")
    op.drop_table("sale_status_history")
    op.drop_index("ix_sales_delivered_date", table_name="sales")
    op.drop_index("ix_sales_promised_delivery_date", table_name="sales")
    op.drop_index("ix_sales_status", table_name="sales")
    op.drop_constraint("ck_sales_status", "sales", type_="check")
    for col in (
        "loss_amount",
        "hours_returned",
        "supplies_returned",
        "materials_returned",
        "cancelled_at",
        "cancel_reason",
        "delivered_date",
        "promised_delivery_date",
        "status",
    ):
        op.drop_column("sales", col)
