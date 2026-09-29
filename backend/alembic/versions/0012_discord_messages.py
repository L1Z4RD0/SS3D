"""discord_messages: qué aviso de Discord anunció cada pedido

Revision ID: 0012_discord_messages
Revises: 0011_order_status
Create Date: 2026-09-29

Solo crea una tabla nueva; no toca ninguna existente. Así, si esta migración todavía no
se aplicó, lo único que deja de funcionar es el aviso en Discord.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012_discord_messages"
down_revision = "0011_order_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discord_messages",
        sa.Column("sale_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Supabase expone las tablas por su API pública; sin políticas, RLS la deja cerrada.
    # El backend entra como dueño de la tabla, así que no le afecta.
    op.execute("ALTER TABLE discord_messages ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("discord_messages")
