from decimal import Decimal

from app.core.config import Settings
from app.schemas import MarketSnapshot, RiskResult, TradeDecisionPayload


class RiskManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(
        self,
        decision: TradeDecisionPayload,
        snapshot: MarketSnapshot,
        max_position_krw: int | None = None,
    ) -> RiskResult:
        reasons: list[str] = []
        price = decision.limit_price or snapshot.price
        notional = Decimal(decision.quantity) * price
        position_limit = Decimal(max_position_krw or self.settings.max_position_krw)

        if decision.action == "HOLD":
            return RiskResult(status="APPROVED", reasons=["Hold decision."], notional_krw=Decimal("0"))

        if decision.quantity <= 0:
            reasons.append("Quantity must be positive for executable decisions.")
        if decision.confidence < self.settings.min_decision_confidence:
            reasons.append("Decision confidence is below the configured threshold.")
        if notional > Decimal(self.settings.max_order_krw):
            reasons.append("Order notional exceeds MAX_ORDER_KRW.")
        if notional > position_limit:
            reasons.append("Order notional exceeds max position limit.")
        if decision.require_human_approval:
            reasons.append("Agent requested human approval.")
        if self.settings.broker_mode == "creon" and not self.settings.live_trading_enabled:
            reasons.append("Live trading approvals are not enabled.")

        if reasons:
            status = "NEEDS_APPROVAL" if reasons == ["Agent requested human approval."] else "REJECTED"
            return RiskResult(status=status, reasons=reasons, notional_krw=notional)

        return RiskResult(status="APPROVED", reasons=["All deterministic checks passed."], notional_krw=notional)

