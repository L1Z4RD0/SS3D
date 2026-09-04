"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-03

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failed_login_attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "printers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("purchase_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("lifetime_hours", sa.Numeric(12, 2), nullable=False),
        sa.Column("power_kw", sa.Numeric(8, 3), nullable=False),
        sa.Column("hours_used", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("depreciation_cost_per_hour", sa.Numeric(14, 4), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_printers_user_id", "printers", ["user_id"])

    op.create_table(
        "filaments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("spool_weight_g", sa.Numeric(10, 2), nullable=False, server_default="1000"),
        sa.Column("initial_stock_g", sa.Numeric(10, 2), nullable=False),
        sa.Column("used_g", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("available_g", sa.Numeric(10, 2), nullable=False),
        sa.Column("min_alert_g", sa.Numeric(10, 2), nullable=False),
        sa.Column("spool_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_filaments_user_id", "filaments", ["user_id"])
    op.create_index("ix_filaments_user_active", "filaments", ["user_id", "is_active"])

    op.create_table(
        "supplies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("quantity_available", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("min_alert_qty", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_supplies_user_id", "supplies", ["user_id"])

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

    op.create_table(
        "sales",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("buyer_name", sa.Text(), nullable=True),
        sa.Column(
            "printer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("printers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "filament_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("filaments.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("grams_used", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("print_hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("postprocess_hours", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("base_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("iva_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("iva_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("material_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("depreciation_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("energy_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("postprocess_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("supplies_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("shipping_cost", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("profit", sa.Numeric(14, 2), nullable=False),
        sa.Column("margin_percent", sa.Numeric(6, 2), nullable=False),
        sa.Column("payment_method", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sales_user_id", "sales", ["user_id"])
    op.create_index("ix_sales_sale_date", "sales", ["sale_date"])
    op.create_index("ix_sales_user_date", "sales", ["user_id", "sale_date"])
    op.create_index("ix_sales_printer_id", "sales", ["printer_id"])
    op.create_index("ix_sales_filament_id", "sales", ["filament_id"])

    op.create_table(
        "sale_supplies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "sale_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supply_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("supplies.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity_used", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit_cost_snapshot", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_sale_supplies_sale_id", "sale_supplies", ["sale_id"])


def downgrade() -> None:
    op.drop_table("sale_supplies")
    op.drop_table("sales")
    op.drop_table("calculator_settings")
    op.drop_table("supplies")
    op.drop_table("filaments")
    op.drop_table("printers")
    op.drop_table("audit_logs")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("roles")
