"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False, index=True),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("agent_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "trade_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False, index=True),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=False),
        sa.Column("risk_status", sa.String(length=16), nullable=False),
        sa.Column("risk_reasons", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("decision_id", sa.Integer(), sa.ForeignKey("trade_decisions.id"), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False, index=True),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.String(length=16), nullable=False),
        sa.Column("limit_price", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False, unique=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("market_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("positions")
    op.drop_table("orders")
    op.drop_table("trade_decisions")
    op.drop_table("agent_runs")

