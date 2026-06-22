from decimal import Decimal

from app.core.config import Settings
from app.schemas import AgentVerdict, MarketSnapshot, TradeDecisionPayload
from app.services.risk import RiskManager


def _decision(confidence: float = 0.9, quantity: int = 1) -> TradeDecisionPayload:
    return TradeDecisionPayload(
        symbol="A005930",
        action="BUY",
        quantity=quantity,
        order_type="LIMIT",
        limit_price=Decimal("70000"),
        confidence=confidence,
        thesis="test",
        stop_loss_pct=2,
        take_profit_pct=4,
        require_human_approval=False,
        agent_votes=[
            AgentVerdict(
                role="test",
                verdict="bullish",
                confidence=confidence,
                reasons=["test"],
                risk_notes=[],
            )
        ],
    )


def test_rejects_low_confidence() -> None:
    settings = Settings(openai_api_key=None, min_decision_confidence=0.8)
    snapshot = MarketSnapshot(symbol="A005930", price=Decimal("70000"), source="test")
    result = RiskManager(settings).evaluate(_decision(confidence=0.5), snapshot)
    assert result.status == "REJECTED"


def test_approves_small_order() -> None:
    settings = Settings(openai_api_key=None, max_order_krw=1000000, min_decision_confidence=0.5)
    snapshot = MarketSnapshot(symbol="A005930", price=Decimal("70000"), source="test")
    result = RiskManager(settings).evaluate(_decision(confidence=0.8), snapshot)
    assert result.status == "APPROVED"


def test_rejects_user_order_limit() -> None:
    settings = Settings(openai_api_key=None, max_order_krw=1000000, min_decision_confidence=0.5)
    snapshot = MarketSnapshot(symbol="A005930", price=Decimal("70000"), source="test")
    result = RiskManager(settings).evaluate(
        _decision(confidence=0.8),
        snapshot,
        max_order_krw=50000,
    )
    assert result.status == "REJECTED"
    assert "Order notional exceeds max order limit." in result.reasons


def test_user_manual_approval_returns_needs_approval() -> None:
    settings = Settings(openai_api_key=None, max_order_krw=1000000, min_decision_confidence=0.5)
    snapshot = MarketSnapshot(symbol="A005930", price=Decimal("70000"), source="test")
    result = RiskManager(settings).evaluate(
        _decision(confidence=0.8),
        snapshot,
        require_manual_approval=True,
    )
    assert result.status == "NEEDS_APPROVAL"
    assert "User safety setting requires manual approval." in result.reasons


def test_creon_gateway_requires_user_live_trading_opt_in() -> None:
    settings = Settings(
        openai_api_key=None,
        broker_mode="creon_gateway",
        allow_live_trading=True,
        i_understand_loss_risk=True,
        max_order_krw=1000000,
        min_decision_confidence=0.5,
    )
    snapshot = MarketSnapshot(symbol="A005930", price=Decimal("70000"), source="test")
    result = RiskManager(settings).evaluate(
        _decision(confidence=0.8),
        snapshot,
        live_trading_opt_in=False,
    )
    assert result.status == "REJECTED"
    assert "User live trading opt-in is disabled." in result.reasons
