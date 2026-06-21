from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Action = Literal["BUY", "SELL", "HOLD"]
RiskStatus = Literal["APPROVED", "REJECTED", "NEEDS_APPROVAL"]
UserRole = Literal["user", "admin"]
OrderStatus = Literal[
    "PENDING_APPROVAL",
    "APPROVED",
    "SUBMITTING",
    "SUBMITTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "REJECTED",
    "SUBMISSION_FAILED",
    "CANCELED",
]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        local_part, separator, domain = normalized.partition("@")
        if not separator or not local_part or "." not in domain or domain.startswith("."):
            raise ValueError("A valid email address is required.")
        return normalized


class UserProfile(BaseModel):
    id: int
    username: str
    email: str
    role: UserRole


class UserProfileUpdate(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    new_password: str | None = Field(default=None, min_length=12, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        local_part, separator, domain = normalized.partition("@")
        if not separator or not local_part or "." not in domain or domain.startswith("."):
            raise ValueError("A valid email address is required.")
        return normalized


class LoginResponse(BaseModel):
    csrf_token: str
    token_type: Literal["cookie"] = "cookie"
    user: UserProfile


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


AssistantIntent = Literal[
    "assistant_workspace",
    "trade_decision",
    "portfolio_review",
    "order_review",
    "decision_history",
    "web_research",
    "system_status",
]
ArtifactType = Literal[
    "metric_grid",
    "table",
    "line_chart",
    "bar_chart",
    "pie_chart",
    "web_tab",
    "decision_card",
]


class AssistantQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    symbol: str | None = Field(default=None, min_length=2, max_length=16)
    quantity: int = Field(default=1, ge=0)
    max_position_krw: int | None = Field(default=None, ge=0)
    last_price: Decimal | None = Field(default=None, ge=0)


class AssistantArtifact(BaseModel):
    id: str
    type: ArtifactType
    title: str
    description: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AssistantQueryResponse(BaseModel):
    answer: str
    intent: AssistantIntent
    artifacts: list[AssistantArtifact] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)
    decision: DecisionResponse | None = None


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
    status: OrderStatus | str
    broker_order_id: str | None
    message: str | None
    approved_at: datetime | None = None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    rejected_at: datetime | None = None
    failed_at: datetime | None = None
    canceled_at: datetime | None = None
    last_status_at: datetime | None = None
    submission_attempts: int = 0
    can_approve: bool = False
    can_cancel: bool = False
    is_terminal: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class OrderEventView(BaseModel):
    id: int
    order_id: int
    from_status: str | None
    to_status: str
    event_type: str
    message: str | None
    broker_order_id: str | None
    event_payload: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PositionView(BaseModel):
    symbol: str
    quantity: int
    avg_price: Decimal
    market_price: Decimal

    model_config = {"from_attributes": True}


class DecisionListItem(BaseModel):
    id: int
    symbol: str
    action: str
    quantity: int
    confidence: float
    risk_status: str
    risk_reasons: list[str]
    created_at: str


class TransactionView(BaseModel):
    id: int
    symbol: str
    side: str
    quantity: int
    order_type: str
    limit_price: Decimal | None
    status: str
    mode: str
    broker_order_id: str | None
    message: str | None
    approved_at: datetime | None = None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    rejected_at: datetime | None = None
    failed_at: datetime | None = None
    canceled_at: datetime | None = None
    last_status_at: datetime | None = None
    submission_attempts: int = 0
    can_approve: bool = False
    can_cancel: bool = False
    is_terminal: bool = False
    created_at: datetime


class DashboardSummary(BaseModel):
    user: UserProfile
    broker_mode: str
    live_trading_enabled: bool
    auto_execute: bool
    total_market_value: Decimal
    total_cost_basis: Decimal
    unrealized_pnl: Decimal
    positions_count: int
    open_orders_count: int
    filled_orders_count: int
    rejected_orders_count: int
    recent_transactions: list[TransactionView]
    positions: list[PositionView]
    recent_decisions: list[DecisionListItem]
