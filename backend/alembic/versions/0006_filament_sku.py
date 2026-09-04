"""add sku to filaments

Revision ID: 0006_filament_sku
Revises: 0005_supply_purchase_cost
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "0006_filament_sku"
down_revision = "0005_supply_purchase_cost"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filaments", sa.Column("sku", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("filaments", "sku")
