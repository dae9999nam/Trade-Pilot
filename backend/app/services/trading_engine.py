from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker.base import Broker, BrokerOrder
from app.core.config import Settings
from app.models import AgentRun, Order, Position, TradeDecision
from app.schemas import (
    DecisionRequest,
    DecisionResponse,
    MarketSnapshot,
    OrderCreate,
    TradeDecisionPayload,
)
from app.services.agent_orchestrator import AgentOrchestrator
from app.services.order_lifecycle import (
    ORDER_APPROVED,
    ORDER_CANCELED,
    ORDER_FILLED,
    ORDER_PARTIALLY_FILLED,
    ORDER_PENDING_APPROVAL,
    ORDER_REJECTED,
    ORDER_SUBMISSION_FAILED,
    ORDER_SUBMITTED,
    ORDER_SUBMITTING,
    can_approve,
    can_cancel,
    can_transition,
    initialize_order_status,
    is_terminal,
    transition_order,
)
from app.services.risk import RiskManager
from app.services.trading_safety import (
    effective_live_trading_enabled,
    effective_max_order_krw,
    effective_max_position_krw,
    effective_min_decision_confidence,
    get_or_create_user_trading_settings,
)


class TradingEngine:
    def __init__(self, db: Session, broker: Broker, settings: Settings, user_id: int) -> None:
        self.db = db
        self.broker = broker
        self.settings = settings
        self.user_id = user_id
        self.orchestrator = AgentOrchestrator(settings)
        self.risk = RiskManager(settings)

    def run_decision(self, request: DecisionRequest, snapshot: MarketSnapshot) -> DecisionResponse:
        decision = self.orchestrator.run(request, snapshot)
        safety = get_or_create_user_trading_settings(self.db, self.user_id, self.settings)
        risk_result = self.risk.evaluate(
            decision,
            snapshot,
            max_position_krw=effective_max_position_krw(
                safety,
                self.settings,
                request.max_position_krw,
            ),
            max_order_krw=effective_max_order_krw(safety, self.settings),
            min_decision_confidence=effective_min_decision_confidence(safety, self.settings),
            require_manual_approval=safety.require_manual_approval,
            live_trading_opt_in=safety.live_trading_opt_in,
        )

        agent_run = AgentRun(
            user_id=self.user_id,
            symbol=request.symbol.upper(),
            request_payload=request.model_dump(mode="json"),
            agent_payload=decision.model_dump(mode="json"),
        )
        self.db.add(agent_run)

        decision_row = TradeDecision(
            user_id=self.user_id,
            symbol=decision.symbol,
            action=decision.action,
            quantity=decision.quantity,
            confidence=decision.confidence,
            thesis=decision.thesis,
            risk_status=risk_result.status,
            risk_reasons=risk_result.reasons,
            raw_payload=decision.model_dump(mode="json"),
        )
        self.db.add(decision_row)
        self.db.flush()

        order_id: int | None = None
        if (
            self.settings.auto_execute
            and risk_result.status == "APPROVED"
            and decision.action in {"BUY", "SELL"}
        ):
            order = self._create_order_from_decision(decision_row.id, decision)
            order_id = order.id

        self.db.commit()
        return DecisionResponse(
            id=decision_row.id,
            risk_status=risk_result.status,
            risk_reasons=risk_result.reasons,
            decision=decision,
            order_id=order_id,
        )

    def create_manual_order(self, order_create: OrderCreate) -> Order:
        order = Order(
            user_id=self.user_id,
            mode=self.settings.broker_mode,
            symbol=order_create.symbol.upper(),
            side=order_create.side,
            quantity=order_create.quantity,
            order_type=order_create.order_type,
            limit_price=order_create.limit_price,
            status=ORDER_PENDING_APPROVAL,
        )
        self.db.add(order)
        self.db.flush()
        initialize_order_status(
            self.db,
            order,
            ORDER_PENDING_APPROVAL,
            event_type="manual_order_staged",
            message="Manual order staged.",
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def approve_order(self, order_id: int) -> Order:
        order = self._get_user_order(order_id)
        if not can_approve(order):
            return order

        safety_failure = self._order_safety_failure(order)
        if safety_failure:
            transition_order(
                self.db,
                order,
                ORDER_REJECTED,
                event_type="order_rejected_by_safety",
                message=safety_failure,
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        transition_order(
            self.db,
            order,
            ORDER_APPROVED,
            event_type="order_approved",
            message="Order approved for broker submission.",
        )
        order.submission_attempts += 1
        transition_order(
            self.db,
            order,
            ORDER_SUBMITTING,
            event_type="broker_submit_started",
            message=f"Submitting order to {self.settings.broker_mode}.",
        )
        self.db.flush()

        try:
            result = self.broker.place_order(
                BrokerOrder(
                    symbol=order.symbol,
                    side=order.side,  # type: ignore[arg-type]
                    quantity=order.quantity,
                    order_type=order.order_type,  # type: ignore[arg-type]
                    limit_price=order.limit_price,
                )
            )
        except Exception as exc:
            transition_order(
                self.db,
                order,
                ORDER_SUBMISSION_FAILED,
                event_type="broker_submit_failed",
                message=str(exc),
                event_payload={"exception_type": type(exc).__name__},
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        next_status = self._normalize_broker_status(result.status)
        transition_order(
            self.db,
            order,
            next_status,
            event_type="broker_submit_result",
            message=result.message,
            broker_order_id=result.broker_order_id,
            event_payload={"broker_status": result.status},
        )

        if next_status == ORDER_FILLED and self.settings.broker_mode == "paper":
            self._upsert_paper_position(order)

        self.db.commit()
        self.db.refresh(order)
        return order

    def cancel_order(self, order_id: int) -> Order:
        order = self._get_user_order(order_id)
        if not can_cancel(order):
            return order

        if order.status in {ORDER_PENDING_APPROVAL, ORDER_APPROVED, ORDER_SUBMISSION_FAILED}:
            transition_order(
                self.db,
                order,
                ORDER_CANCELED,
                event_type="order_canceled",
                message="Order canceled before reliable broker acceptance.",
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        if not order.broker_order_id:
            transition_order(
                self.db,
                order,
                ORDER_CANCELED,
                event_type="order_canceled",
                message="Order canceled locally because no broker order ID is available.",
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        try:
            result = self.broker.cancel_order(order.broker_order_id)
        except Exception as exc:
            transition_order(
                self.db,
                order,
                order.status,
                event_type="broker_cancel_failed",
                message=str(exc),
                event_payload={"exception_type": type(exc).__name__},
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        next_status = self._normalize_broker_status(result.status)
        message = result.message
        if not can_transition(order.status, next_status):
            message = f"{result.message} Broker status {result.status} cannot transition from {order.status}."
            next_status = order.status
        transition_order(
            self.db,
            order,
            next_status,
            event_type="broker_cancel_result",
            message=message,
            broker_order_id=result.broker_order_id,
            event_payload=self._broker_status_payload(result.status, result.raw_payload),
        )
        self.db.commit()
        self.db.refresh(order)
        return order

    def refresh_order_status(self, order_id: int) -> Order:
        order = self._get_user_order(order_id)
        if is_terminal(order):
            return order

        if not order.broker_order_id:
            transition_order(
                self.db,
                order,
                order.status,
                event_type="order_status_refreshed",
                message="No broker status is available for this local order state.",
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        try:
            result = self.broker.get_order_status(order.broker_order_id)
        except Exception as exc:
            transition_order(
                self.db,
                order,
                order.status,
                event_type="broker_status_refresh_failed",
                message=str(exc),
                event_payload={"exception_type": type(exc).__name__},
            )
            self.db.commit()
            self.db.refresh(order)
            return order

        previous_status = order.status
        next_status = self._normalize_broker_status(result.status)
        message = result.message
        if not can_transition(order.status, next_status):
            message = f"{result.message} Broker status {result.status} cannot transition from {order.status}."
            next_status = order.status
        transition_order(
            self.db,
            order,
            next_status,
            event_type="broker_status_refreshed",
            message=message,
            broker_order_id=result.broker_order_id,
            event_payload=self._broker_status_payload(result.status, result.raw_payload),
        )

        if (
            previous_status != ORDER_FILLED
            and next_status == ORDER_FILLED
            and self.settings.broker_mode == "paper"
        ):
            self._upsert_paper_position(order)

        self.db.commit()
        self.db.refresh(order)
        return order

    def _create_order_from_decision(self, decision_id: int, decision: TradeDecisionPayload) -> Order:
        order = Order(
            user_id=self.user_id,
            decision_id=decision_id,
            mode=self.settings.broker_mode,
            symbol=decision.symbol,
            side=decision.action,
            quantity=decision.quantity,
            order_type=decision.order_type,
            limit_price=decision.limit_price,
            status=ORDER_PENDING_APPROVAL,
        )
        self.db.add(order)
        self.db.flush()
        initialize_order_status(
            self.db,
            order,
            ORDER_PENDING_APPROVAL,
            event_type="ai_decision_order_created",
            message="Created from approved AI decision.",
        )
        self.approve_order(order.id)
        return order

    def _get_user_order(self, order_id: int) -> Order:
        order = self.db.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == self.user_id)
        )
        if order is None:
            raise ValueError("Order not found.")
        return order

    def _order_safety_failure(self, order: Order) -> str | None:
        safety = get_or_create_user_trading_settings(self.db, self.user_id, self.settings)
        price = order.limit_price
        if price is None:
            price = self.broker.get_quote(order.symbol).price
        notional = Decimal(order.quantity) * price
        if notional > Decimal(effective_max_order_krw(safety, self.settings)):
            return "Order notional exceeds max order limit."
        if self.settings.broker_mode in {"creon", "creon_gateway"}:
            if not self.settings.live_trading_enabled:
                return "System live trading gate is disabled."
            if not effective_live_trading_enabled(safety, self.settings):
                return "User live trading opt-in is disabled."
        return None

    def _normalize_broker_status(self, broker_status: str) -> str:
        normalized = broker_status.upper()
        if normalized in {ORDER_SUBMITTED, "ACCEPTED"}:
            return ORDER_SUBMITTED
        if normalized in {ORDER_FILLED, "EXECUTED"}:
            return ORDER_FILLED
        if normalized in {ORDER_PARTIALLY_FILLED, "PARTIAL", "PARTIALLY_FILLED"}:
            return ORDER_PARTIALLY_FILLED
        if normalized in {ORDER_REJECTED, "REJECT"}:
            return ORDER_REJECTED
        if normalized in {ORDER_CANCELED, "CANCELLED"}:
            return ORDER_CANCELED
        return ORDER_SUBMISSION_FAILED

    def _broker_status_payload(
        self,
        broker_status: str,
        raw_payload: dict | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"broker_status": broker_status}
        if raw_payload:
            payload["raw_payload"] = raw_payload
        return payload

    def _upsert_paper_position(self, order: Order) -> None:
        price = Decimal(order.limit_price or Decimal("0"))
        if price == 0:
            price = Decimal("1")
        position = self.db.scalar(
            select(Position).where(Position.user_id == self.user_id, Position.symbol == order.symbol)
        )
        signed_quantity = order.quantity if order.side == "BUY" else -order.quantity

        if position is None:
            position = Position(
                user_id=self.user_id,
                symbol=order.symbol,
                quantity=signed_quantity,
                avg_price=price,
                market_price=price,
            )
            self.db.add(position)
            return

        new_quantity = position.quantity + signed_quantity
        if new_quantity <= 0:
            position.quantity = 0
            position.market_price = price
            return

        if signed_quantity < 0:
            position.quantity = new_quantity
            position.market_price = price
            return

        current_cost = Decimal(position.quantity) * position.avg_price
        added_cost = Decimal(signed_quantity) * price
        position.quantity = new_quantity
        position.avg_price = (current_cost + added_cost) / Decimal(new_quantity)
        position.market_price = price
