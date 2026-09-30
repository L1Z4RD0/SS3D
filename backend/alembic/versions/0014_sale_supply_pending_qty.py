"""sale_supplies.pending_qty + cost_adjustment: insumos usados sin stock (costo provisional)

Revision ID: 0014_supply_pending_qty
Revises: 0013_filament_color_hex
Create Date: 2026-09-30

Dos columnas nuevas con valor 0 por defecto: todas las líneas existentes quedan con costo
definitivo, exactamente como estaban.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_supply_pending_qty"
down_revision = "0013_filament_color_hex"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sale_supplies",
        sa.Column("pending_qty", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "sale_supplies",
        sa.Column("cost_adjustment", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("sale_supplies", "cost_adjustment")
    op.drop_column("sale_supplies", "pending_qty")
