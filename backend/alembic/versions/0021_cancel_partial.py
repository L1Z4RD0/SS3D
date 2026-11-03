"""sales: cuánto se alcanzó a imprimir de un pedido cancelado con la pieza dañada

Revision ID: 0021_cancel_partial
Revises: 0020_cash_box
Create Date: 2026-11-03

Cuatro columnas nuevas y opcionales en sales (NULL en todos los pedidos existentes). No
toca datos existentes: los cancelados anteriores siguen calculándose como hasta ahora.
- cancel_printed_percent: % de la pieza que se alcanzó a imprimir (1 a 100).
- cancel_print_hours: horas de impresión que se alcanzaron a usar.
- cancel_postprocess_done: si se alcanzó a hacer el postprocesado.
- cancel_discard_reason: motivo del descarte (regalada, danada, desechada u otro).
"""
import sqlalchemy as sa
from alembic import op

revision = "0021_cancel_partial"
down_revision = "0020_cash_box"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("cancel_printed_percent", sa.Numeric(5, 2), nullable=True))
    op.add_column("sales", sa.Column("cancel_print_hours", sa.Numeric(10, 2), nullable=True))
    op.add_column("sales", sa.Column("cancel_postprocess_done", sa.Boolean(), nullable=True))
    op.add_column("sales", sa.Column("cancel_discard_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales", "cancel_discard_reason")
    op.drop_column("sales", "cancel_postprocess_done")
    op.drop_column("sales", "cancel_print_hours")
    op.drop_column("sales", "cancel_printed_percent")
