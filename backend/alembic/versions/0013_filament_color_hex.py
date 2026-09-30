"""filaments.color_hex: tono exacto elegido con el selector RGB

Revision ID: 0013_filament_color_hex
Revises: 0012_discord_messages
Create Date: 2026-09-30

Columna nueva y opcional. Los filamentos existentes quedan en NULL y siguen mostrando el
color del catálogo según su nombre, igual que antes.
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_filament_color_hex"
down_revision = "0012_discord_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("filaments", sa.Column("color_hex", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("filaments", "color_hex")
