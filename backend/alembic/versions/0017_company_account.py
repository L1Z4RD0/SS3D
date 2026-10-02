"""Cuenta Empresa, delivery por venta y gastos de la Empresa (módulo beta de Reparto)

Revision ID: 0017_company_account
Revises: 0016_sale_risk
Create Date: 2026-10-01

- users.is_company: la cuenta Olzer pasa a llamarse Simple_Solutions3D y queda marcada
  como Empresa (misma contraseña, mismas asignaciones de observador).
- sales.delivery_by / delivery_amount: registro de quién hizo el delivery y cuánto se le
  devuelve (no entra en precio, costos ni ganancia).
- company_expenses: compras/gastos de la Empresa para el Reparto (beta).
Todo es aditivo: columnas con valor por defecto y una tabla nueva.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017_company_account"
down_revision = "0016_sale_risk"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("users", sa.Column("is_company", sa.Boolean(), nullable=False, server_default=sa.false()))
    # Olzer pasa a ser la cuenta de la Empresa (si existe y el nombre nuevo está libre).
    op.execute(
        """
        UPDATE users SET username = 'Simple_Solutions3D', is_company = true
        WHERE lower(username) = 'olzer'
          AND NOT EXISTS (SELECT 1 FROM users u2 WHERE u2.username = 'Simple_Solutions3D')
        """
    )
    op.add_column("sales", sa.Column("delivery_by", sa.Text(), nullable=True))
    op.add_column("sales", sa.Column("delivery_amount", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.create_table(
        "company_expenses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_by", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_company_expenses_expense_date", "company_expenses", ["expense_date"])
    op.execute("ALTER TABLE company_expenses ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("company_expenses")
    op.drop_column("sales", "delivery_amount")
    op.drop_column("sales", "delivery_by")
    op.execute("UPDATE users SET username = 'Olzer' WHERE is_company AND username = 'Simple_Solutions3D'")
    op.drop_column("users", "is_company")
