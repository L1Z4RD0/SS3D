"""sales: fecha máxima de pago y fecha de cobro de los pedidos "Por cobrar"

Revision ID: 0022_payment_due
Revises: 0021_cancel_partial
Create Date: 2026-11-05

Dos columnas nuevas y opcionales en sales (NULL en todos los pedidos existentes). No toca
datos existentes.
- payment_due_date: hasta cuándo tiene plazo para pagar un pedido entregado "Por cobrar".
- paid_date: día en que se cobró un pedido que estaba "Por cobrar" (al entregarlo o
  después). El Reparto lo cuenta en el mes de este día; si es NULL, en el de la entrega.
"""
import sqlalchemy as sa
from alembic import op

revision = "0022_payment_due"
down_revision = "0021_cancel_partial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("payment_due_date", sa.Date(), nullable=True))
    op.add_column("sales", sa.Column("paid_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales", "paid_date")
    op.drop_column("sales", "payment_due_date")
