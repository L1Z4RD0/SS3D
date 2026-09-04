"""add quotes, quote_items and business_profiles

Revision ID: 0003_quotes_business_profile
Revises: 0002_drop_calculator_settings
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_quotes_business_profile"
down_revision = "0002_drop_calculator_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quote_number", sa.Integer(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("quote_date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("iva_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("iva_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "quote_number", name="uq_quotes_user_number"),
    )
    op.create_index("ix_quotes_user_id", "quotes", ["user_id"])

    op.create_table(
        "quote_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "quote_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("quotes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_quote_items_quote_id", "quote_items", ["quote_id"])

    op.create_table(
        "business_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("business_name", sa.Text(), nullable=True),
        sa.Column("logo_data_url", sa.Text(), nullable=True),
        sa.UniqueConstraint("user_id", name="uq_business_profiles_user_id"),
    )


def downgrade() -> None:
    op.drop_table("business_profiles")
    op.drop_table("quote_items")
    op.drop_table("quotes")
