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
    OrderApprovalPreview,
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
    record_order_event,
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


class OrderNotFoundError(ValueError):
    pass


class OrderApprovalConfirmationError(ValueError):
    pass


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

    def preview_order_approval(self, order_id: int) -> OrderApprovalPreview:
        order = self._get_user_order(order_id)
        preview = self._build_order_approval_preview(order)
        record_order_event(
            self.db,
            order,
            event_type="order_approval_previewed",
            message="Order approval preview generated.",
            event_payload=self._approval_audit_payload(preview),
        )
        self.db.commit()
        return preview

    def approve_order(self, order_id: int, confirmation_text: str) -> Order:
        order = self._get_user_order(order_id)
        if not can_approve(order):
            return order

        preview = self._build_order_approval_preview(order)
        if confirmation_text.strip() != preview.confirmation_text:
            record_order_event(
                self.db,
                order,
                event_type="order_approval_confirmation_failed",
                message="Order approval confirmation text did not match.",
                event_payload=self._approval_audit_payload(preview),
            )
            self.db.commit()
            raise OrderApprovalConfirmationError("Order approval confirmation text did not match.")

        if not preview.can_submit:
            transition_order(
                self.db,
                order,
                ORDER_REJECTED,
                event_type="order_rejected_by_safety",
                message="; ".join(preview.safety_reasons) or "Order safety check blocked submission.",
                event_payload=self._approval_audit_payload(preview),
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
            event_payload=self._approval_audit_payload(preview),
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
            event_payload=self._broker_status_payload(
                result.status,
                result.raw_payload,
                filled_quantity=result.filled_quantity,
                remaining_quantity=result.remaining_quantity,
                as_of=result.as_of,
            ),
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
            event_payload=self._broker_status_payload(
                result.status,
                result.raw_payload,
                filled_quantity=result.filled_quantity,
                remaining_quantity=result.remaining_quantity,
                as_of=result.as_of,
            ),
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
        self.approve_order(order.id, self._approval_confirmation_text(order))
        return order

    def _get_user_order(self, order_id: int) -> Order:
        order = self.db.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == self.user_id)
        )
        if order is None:
            raise OrderNotFoundError("Order not found.")
        return order

    def _build_order_approval_preview(self, order: Order) -> OrderApprovalPreview:
        price = self._approval_price(order)
        safety_reasons = self._order_safety_reasons(order, price)
        return OrderApprovalPreview(
            order_id=order.id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type=order.order_type,
            limit_price=order.limit_price,
            estimated_price=price,
            estimated_notional_krw=Decimal(order.quantity) * price,
            broker_mode=self.settings.broker_mode,
            system_live_trading_enabled=self.settings.live_trading_enabled,
            effective_live_trading_enabled=effective_live_trading_enabled(
                get_or_create_user_trading_settings(self.db, self.user_id, self.settings),
                self.settings,
            ),
            safety_status="BLOCKED" if safety_reasons else "PASS",
            safety_reasons=safety_reasons,
            confirmation_text=self._approval_confirmation_text(order),
            can_submit=can_approve(order) and not safety_reasons,
        )

    def _approval_price(self, order: Order) -> Decimal:
        if order.limit_price is not None:
            return order.limit_price
        return self.broker.get_quote(order.symbol).price

    def _order_safety_reasons(self, order: Order, price: Decimal) -> list[str]:
        safety = get_or_create_user_trading_settings(self.db, self.user_id, self.settings)
        notional = Decimal(order.quantity) * price
        reasons: list[str] = []
        if notional > Decimal(effective_max_order_krw(safety, self.settings)):
            reasons.append("Order notional exceeds max order limit.")
        if self.settings.broker_mode in {"creon", "creon_gateway"}:
            if not self.settings.live_trading_enabled:
                reasons.append("System live trading gate is disabled.")
            elif not effective_live_trading_enabled(safety, self.settings):
                reasons.append("User live trading opt-in is disabled.")
        return reasons

    def _approval_confirmation_text(self, order: Order) -> str:
        return f"APPROVE {order.id}"

    def _approval_audit_payload(self, preview: OrderApprovalPreview) -> dict[str, object]:
        return {
            "actor_user_id": self.user_id,
            "order_id": preview.order_id,
            "symbol": preview.symbol,
            "side": preview.side,
            "quantity": preview.quantity,
            "order_type": preview.order_type,
            "estimated_price": str(preview.estimated_price),
            "estimated_notional_krw": str(preview.estimated_notional_krw),
            "broker_mode": preview.broker_mode,
            "system_live_trading_enabled": preview.system_live_trading_enabled,
            "effective_live_trading_enabled": preview.effective_live_trading_enabled,
            "safety_status": preview.safety_status,
            "safety_reasons": preview.safety_reasons,
            "confirmation_required": True,
        }

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
        *,
        filled_quantity: int | None = None,
        remaining_quantity: int | None = None,
        as_of: object = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"broker_status": broker_status}
        if filled_quantity is not None:
            payload["filled_quantity"] = filled_quantity
        if remaining_quantity is not None:
            payload["remaining_quantity"] = remaining_quantity
        if as_of is not None:
            payload["as_of"] = as_of.isoformat() if hasattr(as_of, "isoformat") else str(as_of)
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
