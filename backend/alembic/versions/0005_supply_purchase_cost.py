"""add purchase_quantity/purchase_total_cost to supplies (unit_cost is now derived)

Revision ID: 0005_supply_purchase_cost
Revises: 0004_sale_filaments_catalog
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "0005_supply_purchase_cost"
down_revision = "0004_sale_filaments_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplies", sa.Column("purchase_quantity", sa.Numeric(10, 2), nullable=True))
    op.add_column("supplies", sa.Column("purchase_total_cost", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("supplies", "purchase_total_cost")
    op.drop_column("supplies", "purchase_quantity")
