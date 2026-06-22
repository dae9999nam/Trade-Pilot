"""user trading safety settings

Revision ID: 0004_user_trading_settings
Revises: 0003_order_lifecycle
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_user_trading_settings"
down_revision = "0003_order_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_trading_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("max_order_krw", sa.Integer(), nullable=False),
        sa.Column("max_position_krw", sa.Integer(), nullable=False),
        sa.Column("min_decision_confidence", sa.Float(), nullable=False),
        sa.Column("require_manual_approval", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("live_trading_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", name="uq_user_trading_settings_user_id"),
    )
    op.create_index("ix_user_trading_settings_user_id", "user_trading_settings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_trading_settings_user_id", table_name="user_trading_settings")
    op.drop_table("user_trading_settings")
