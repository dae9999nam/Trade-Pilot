from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["BUY", "SELL", "HOLD"]
RiskStatus = Literal["APPROVED", "REJECTED", "NEEDS_APPROVAL"]


class DecisionRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=16)
    quantity: int = Field(default=1, ge=0)
    max_position_krw: int | None = Field(default=None, ge=0)
    last_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class MarketSnapshot(BaseModel):
    symbol: str
    price: Decimal
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    volume: int | None = None
    source: str


class AgentVerdict(BaseModel):
    role: str
    verdict: Literal["bullish", "bearish", "neutral", "block"]
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class TradeDecisionPayload(BaseModel):
    symbol: str
    action: Action
    quantity: int = Field(ge=0)
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: Decimal | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1)
    thesis: str
    stop_loss_pct: float | None = Field(default=None, ge=0, le=100)
    take_profit_pct: float | None = Field(default=None, ge=0, le=100)
    require_human_approval: bool
    agent_votes: list[AgentVerdict]


class RiskResult(BaseModel):
    status: RiskStatus
    reasons: list[str]
    notional_krw: Decimal


class DecisionResponse(BaseModel):
    id: int
    risk_status: RiskStatus
    risk_reasons: list[str]
    decision: TradeDecisionPayload
    order_id: int | None = None


class OrderCreate(BaseModel):
    symbol: str = Field(min_length=2, max_length=16)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"] = "LIMIT"
    limit_price: Decimal | None = Field(default=None, ge=0)


class OrderView(BaseModel):
    id: int
    mode: str
    symbol: str
    side: str
    quantity: int
    order_type: str
    limit_price: Decimal | None
    status: str
    broker_order_id: str | None
    message: str | None

    model_config = {"from_attributes": True}


class PositionView(BaseModel):
    symbol: str
    quantity: int
    avg_price: Decimal
    market_price: Decimal

    model_config = {"from_attributes": True}

