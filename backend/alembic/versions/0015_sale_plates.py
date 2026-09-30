"""sale_plates + sale_plate_filaments: planchas adicionales y reimpresiones de un pedido

Revision ID: 0015_sale_plates
Revises: 0014_supply_pending_qty
Create Date: 2026-09-30

Solo crea tablas nuevas. Los pedidos existentes no tienen planchas adicionales y siguen
funcionando exactamente igual (su impresora, horas y filamentos son la plancha principal).
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_sale_plates"
down_revision = "0014_supply_pending_qty"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "sale_plates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sale_id", UUID, sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("printer_id", UUID, sa.ForeignKey("printers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("print_hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("is_reprint", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("material_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("depreciation_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("energy_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sale_plates_sale_id", "sale_plates", ["sale_id"])
    op.create_index("ix_sale_plates_printer_id", "sale_plates", ["printer_id"])
    op.create_table(
        "sale_plate_filaments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("plate_id", UUID, sa.ForeignKey("sale_plates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filament_id", UUID, sa.ForeignKey("filaments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("grams_used", sa.Numeric(10, 2), nullable=False),
        sa.Column("material_cost_snapshot", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_sale_plate_filaments_plate_id", "sale_plate_filaments", ["plate_id"])
    op.create_index("ix_sale_plate_filaments_filament_id", "sale_plate_filaments", ["filament_id"])
    # Igual que discord_messages: cerradas a la API pública de Supabase (el backend entra
    # como dueño y no le afecta).
    op.execute("ALTER TABLE sale_plates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sale_plate_filaments ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("sale_plate_filaments")
    op.drop_table("sale_plates")
