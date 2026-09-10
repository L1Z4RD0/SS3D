"""enforce sku uniqueness per user on filaments

Revision ID: 0007_filament_sku_unique
Revises: 0006_filament_sku
Create Date: 2026-09-09

"""
from alembic import op

revision = "0007_filament_sku_unique"
down_revision = "0006_filament_sku"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_filaments_user_sku", "filaments", ["user_id", "sku"])


def downgrade() -> None:
    op.drop_constraint("uq_filaments_user_sku", "filaments", type_="unique")
