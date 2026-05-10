from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    request_payload: Mapped[dict] = mapped_column(JsonType)
    agent_payload: Mapped[dict] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TradeDecision(Base):
    __tablename__ = "trade_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column()
    confidence: Mapped[float] = mapped_column()
    thesis: Mapped[str] = mapped_column(Text)
    risk_status: Mapped[str] = mapped_column(String(16))
    risk_reasons: Mapped[list[str]] = mapped_column(JsonType)
    raw_payload: Mapped[dict] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    orders: Mapped[list["Order"]] = relationship(back_populates="decision")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("trade_decisions.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(16))
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[int] = mapped_column()
    order_type: Mapped[str] = mapped_column(String(16))
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    decision: Mapped[TradeDecision | None] = relationship(back_populates="orders")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True)
    quantity: Mapped[int] = mapped_column()
    avg_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    market_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

