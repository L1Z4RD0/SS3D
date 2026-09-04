"""add sale_filaments (multicolor sales) and filament catalogs (brand/material/color)

Revision ID: 0004_sale_filaments_catalog
Revises: 0003_quotes_business_profile
Create Date: 2026-09-04

"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_sale_filaments_catalog"
down_revision = "0003_quotes_business_profile"
branch_labels = None
depends_on = None

BRANDS = ["eSUN", "Creality", "Bambu Lab", "TodoToner", "Sunlu", "Winkle", "Generic"]

MATERIALS = ["PLA", "PLA+", "PLA Lite", "PLA High Speed", "PETG", "ABS", "TPU"]

COLORS = [
    ("Blanco", "#FFFFFF"),
    ("Negro", "#111111"),
    ("Rojo", "#E53935"),
    ("Azul", "#1E88E5"),
    ("Amarillo", "#FDD835"),
    ("Rosa", "#EC407A"),
    ("Café", "#6D4C41"),
    ("Verde", "#43A047"),
    ("Morado", "#8E24AA"),
    ("Naranjo", "#FB8C00"),
    ("Gris", "#9E9E9E"),
    ("Dorado", "#D4AF37"),
]


def upgrade() -> None:
    op.create_table(
        "sale_filaments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "filament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("filaments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("grams_used", sa.Numeric(10, 2), nullable=False),
        sa.Column("material_cost_snapshot", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_sale_filaments_sale_id", "sale_filaments", ["sale_id"])

    brands_table = op.create_table(
        "filament_brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("name", name="uq_filament_brands_name"),
    )
    materials_table = op.create_table(
        "filament_materials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("name", name="uq_filament_materials_name"),
    )
    colors_table = op.create_table(
        "filament_colors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hex_color", sa.Text(), nullable=False),
        sa.UniqueConstraint("name", name="uq_filament_colors_name"),
    )

    op.bulk_insert(brands_table, [{"id": uuid.uuid4(), "name": name} for name in BRANDS])
    op.bulk_insert(materials_table, [{"id": uuid.uuid4(), "name": name} for name in MATERIALS])
    op.bulk_insert(
        colors_table, [{"id": uuid.uuid4(), "name": name, "hex_color": hex_color} for name, hex_color in COLORS]
    )


def downgrade() -> None:
    op.drop_table("filament_colors")
    op.drop_table("filament_materials")
    op.drop_table("filament_brands")
    op.drop_table("sale_filaments")
