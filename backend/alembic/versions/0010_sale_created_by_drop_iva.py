"""sales.created_by_user_id (who registered the sale) + drop users.iva_enabled

Revision ID: 0010_sale_created_by
Revises: 0009_user_iva_enabled
Create Date: 2026-09-27

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_sale_created_by"
down_revision = "0009_user_iva_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Quién registró cada venta (el dueño o un observador que vende con su inventario).
    op.add_column(
        "sales",
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sales_created_by_user_id", "sales", ["created_by_user_id"])
    # Hasta hoy solo el dueño podía registrar ventas: todas las existentes son suyas.
    op.execute("UPDATE sales SET created_by_user_id = user_id")

    # El IVA se sacó de la app (se implementará más adelante); el switch por usuario ya no existe.
    op.drop_column("users", "iva_enabled")


def downgrade() -> None:
    op.add_column("users", sa.Column("iva_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_index("ix_sales_created_by_user_id", table_name="sales")
    op.drop_column("sales", "created_by_user_id")
