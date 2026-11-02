"""cash_box_closings + cash_box_withdrawals: saldo real de la Caja al cierre de mes y retiros

Revision ID: 0020_cash_box
Revises: 0019_sale_source
Create Date: 2026-11-01

Dos tablas nuevas del Reparto (beta). No toca datos existentes.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_cash_box"
down_revision = "0019_sale_source"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "cash_box_closings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("month", sa.Text(), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "cash_box_withdrawals",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("withdrawal_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cash_box_withdrawals_withdrawal_date", "cash_box_withdrawals", ["withdrawal_date"])
    op.execute("ALTER TABLE cash_box_closings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE cash_box_withdrawals ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("cash_box_withdrawals")
    op.drop_table("cash_box_closings")
