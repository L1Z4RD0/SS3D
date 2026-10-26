"""sales.sale_source: de dónde salió la venta (instagram, facebook, personal)

Revision ID: 0019_sale_source
Revises: 0018_last_seen_release
Create Date: 2026-10-26

Columna nueva y opcional: las ventas anteriores quedan en NULL ("Sin registrar"). No toca
datos existentes.
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_sale_source"
down_revision = "0018_last_seen_release"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("sale_source", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales", "sale_source")
