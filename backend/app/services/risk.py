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
        max_order_krw: int | None = None,
        min_decision_confidence: float | None = None,
        require_manual_approval: bool = False,
        live_trading_opt_in: bool = True,
    ) -> RiskResult:
        reject_reasons: list[str] = []
        approval_reasons: list[str] = []
        price = decision.limit_price or snapshot.price
        notional = Decimal(decision.quantity) * price
        order_limit = Decimal(max_order_krw if max_order_krw is not None else self.settings.max_order_krw)
        position_limit = Decimal(max_position_krw or self.settings.max_position_krw)
        confidence_floor = (
            min_decision_confidence
            if min_decision_confidence is not None
            else self.settings.min_decision_confidence
        )

        if decision.action == "HOLD":
            return RiskResult(status="APPROVED", reasons=["Hold decision."], notional_krw=Decimal("0"))

        if decision.quantity <= 0:
            reject_reasons.append("Quantity must be positive for executable decisions.")
        if decision.confidence < confidence_floor:
            reject_reasons.append("Decision confidence is below the configured threshold.")
        if notional > order_limit:
            reject_reasons.append("Order notional exceeds max order limit.")
        if notional > position_limit:
            reject_reasons.append("Order notional exceeds max position limit.")
        if decision.require_human_approval:
            approval_reasons.append("Agent requested human approval.")
        if require_manual_approval:
            approval_reasons.append("User safety setting requires manual approval.")
        if self.settings.broker_mode in {"creon", "creon_gateway"}:
            if not self.settings.live_trading_enabled:
                reject_reasons.append("System live trading gate is disabled.")
            elif not live_trading_opt_in:
                reject_reasons.append("User live trading opt-in is disabled.")

        if reject_reasons:
            return RiskResult(
                status="REJECTED",
                reasons=[*reject_reasons, *approval_reasons],
                notional_krw=notional,
            )
        if approval_reasons:
            return RiskResult(status="NEEDS_APPROVAL", reasons=approval_reasons, notional_krw=notional)

        return RiskResult(status="APPROVED", reasons=["All deterministic checks passed."], notional_krw=notional)
