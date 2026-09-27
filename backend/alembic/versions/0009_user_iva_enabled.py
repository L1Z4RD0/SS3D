"""per-user IVA switch (beta: IVA off by default, admin enables it per user)

Revision ID: 0009_user_iva_enabled
Revises: 0008_watcher_quotes
Create Date: 2026-09-25

"""
import sqlalchemy as sa
from alembic import op

revision = "0009_user_iva_enabled"
down_revision = "0008_watcher_quotes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("iva_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "iva_enabled")
