"""drop calculator_settings (rates/IVA/margins are now fixed backend constants)

Revision ID: 0002_drop_calculator_settings
Revises: 0001_initial_schema
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_drop_calculator_settings"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("calculator_settings")


def downgrade() -> None:
    op.create_table(
        "calculator_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("electricity_rate", sa.Numeric(10, 4), nullable=False),
        sa.Column("labor_rate_per_hour", sa.Numeric(14, 2), nullable=False),
        sa.Column("iva_percent", sa.Numeric(5, 2), nullable=False, server_default="19"),
        sa.Column("margin_scenarios", postgresql.JSONB(), nullable=False),
        sa.Column("default_packaging_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_calculator_settings_user_id"),
    )
