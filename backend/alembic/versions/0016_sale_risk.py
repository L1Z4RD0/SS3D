"""sales.risk_percent + risk_amount: riesgo de fallo cobrado en el precio

Revision ID: 0016_sale_risk
Revises: 0015_sale_plates
Create Date: 2026-10-01

Dos columnas nuevas con 0 por defecto: las ventas anteriores no tenían riesgo y quedan
exactamente igual.
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_sale_risk"
down_revision = "0015_sale_plates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sales", sa.Column("risk_percent", sa.Numeric(5, 2), nullable=False, server_default="0"))
    op.add_column("sales", sa.Column("risk_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("sales", "risk_amount")
    op.drop_column("sales", "risk_percent")
