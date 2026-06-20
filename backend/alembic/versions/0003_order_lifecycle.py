"""order lifecycle metadata

Revision ID: 0003_order_lifecycle
Revises: 0002_user_auth_sessions
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_order_lifecycle"
down_revision = "0002_user_auth_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "last_status_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "orders",
        sa.Column("submission_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "order_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("event_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_events_order_id", "order_events", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_events_order_id", table_name="order_events")
    op.drop_table("order_events")

    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_column("orders", "submission_attempts")
    op.drop_column("orders", "last_status_at")
    op.drop_column("orders", "canceled_at")
    op.drop_column("orders", "failed_at")
    op.drop_column("orders", "rejected_at")
    op.drop_column("orders", "filled_at")
    op.drop_column("orders", "submitted_at")
    op.drop_column("orders", "approved_at")
