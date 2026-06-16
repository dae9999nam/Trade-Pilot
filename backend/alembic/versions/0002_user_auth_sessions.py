"""user auth sessions and ownership

Revision ID: 0002_user_auth_sessions
Revises: 0001_initial
Create Date: 2026-06-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_user_auth_sessions"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_token_hash", sa.String(length=128), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_session_token_hash", "user_sessions", ["session_token_hash"], unique=True)
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    op.add_column("agent_runs", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"])
    op.add_column("trade_decisions", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_trade_decisions_user_id", "trade_decisions", ["user_id"])
    op.add_column("orders", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.add_column("positions", sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.create_index("ix_positions_user_id", "positions", ["user_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.drop_constraint("positions_symbol_key", "positions", type_="unique")
    op.create_unique_constraint("uq_positions_user_symbol", "positions", ["user_id", "symbol"])


def downgrade() -> None:
    op.drop_constraint("uq_positions_user_symbol", "positions", type_="unique")
    if op.get_bind().dialect.name == "postgresql":
        op.create_unique_constraint("positions_symbol_key", "positions", ["symbol"])

    op.drop_index("ix_positions_user_id", table_name="positions")
    op.drop_column("positions", "user_id")
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_column("orders", "user_id")
    op.drop_index("ix_trade_decisions_user_id", table_name="trade_decisions")
    op.drop_column("trade_decisions", "user_id")
    op.drop_index("ix_agent_runs_user_id", table_name="agent_runs")
    op.drop_column("agent_runs", "user_id")

    op.drop_index("ix_user_sessions_expires_at", table_name="user_sessions")
    op.drop_index("ix_user_sessions_session_token_hash", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
