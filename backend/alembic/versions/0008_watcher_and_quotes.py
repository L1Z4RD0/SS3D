"""watcher role + assignments, persistent quote counter, quote document snapshot

Revision ID: 0008_watcher_quotes
Revises: 0007_filament_sku_unique
Create Date: 2026-09-22

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_watcher_quotes"
down_revision = "0007_filament_sku_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rol watcher (solo observa; no puede escribir en datos de nadie).
    roles = sa.table("roles", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("name", sa.Text()))
    conn = op.get_bind()
    exists = conn.execute(sa.text("SELECT 1 FROM roles WHERE name = 'watcher'")).first()
    if not exists:
        op.bulk_insert(roles, [{"id": uuid.uuid4(), "name": "watcher"}])

    # 2. Qué usuarios puede observar cada watcher (lo asigna el administrador).
    op.create_table(
        "watcher_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "watcher_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "observed_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("watcher_user_id", "observed_user_id", name="uq_watcher_assignment"),
    )

    # 3. Contador de cotizaciones por usuario que nunca retrocede. Antes el número
    #    salía de MAX(quote_number)+1, así que al borrar cotizaciones la numeración
    #    se reiniciaba y se repetían códigos ya usados.
    op.add_column("users", sa.Column("last_quote_number", sa.Integer(), nullable=False, server_default="0"))
    conn.execute(
        sa.text(
            "UPDATE users u SET last_quote_number = COALESCE("
            "(SELECT MAX(q.quote_number) FROM quotes q WHERE q.user_id = u.id), 0)"
        )
    )

    # 4. Respaldo del comprobante de la cotización, como texto plano.
    op.add_column("quotes", sa.Column("document_snapshot", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("quotes", "document_snapshot")
    op.drop_column("users", "last_quote_number")
    op.drop_table("watcher_assignments")
    op.execute("DELETE FROM roles WHERE name = 'watcher'")
