"""users.last_seen_release: última ventana de Novedades que vio cada usuario

Revision ID: 0018_last_seen_release
Revises: 0017_company_account
Create Date: 2026-10-02

Columna nueva y opcional (NULL = no ha visto ninguna). No toca datos existentes.
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_last_seen_release"
down_revision = "0017_company_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_release", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_seen_release")
