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
from app.services.risk import RiskManager


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
        risk_result = self.risk.evaluate(decision, snapshot, request.max_position_krw)

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
            status="PENDING_APPROVAL",
            message="Manual order staged.",
        )
        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)
        return order

    def approve_order(self, order_id: int) -> Order:
        order = self.db.scalar(
            select(Order).where(Order.id == order_id, Order.user_id == self.user_id)
        )
        if order is None:
            raise ValueError("Order not found.")
        if order.status not in {"PENDING_APPROVAL", "REJECTED"}:
            return order

        result = self.broker.place_order(
            BrokerOrder(
                symbol=order.symbol,
                side=order.side,  # type: ignore[arg-type]
                quantity=order.quantity,
                order_type=order.order_type,  # type: ignore[arg-type]
                limit_price=order.limit_price,
            )
        )
        order.status = result.status
        order.broker_order_id = result.broker_order_id
        order.message = result.message

        if result.status in {"FILLED", "SUBMITTED"} and self.settings.broker_mode == "paper":
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
            status="PENDING_APPROVAL",
            message="Created from approved AI decision.",
        )
        self.db.add(order)
        self.db.flush()
        self.approve_order(order.id)
        return order

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

        current_cost = Decimal(position.quantity) * position.avg_price
        added_cost = Decimal(max(signed_quantity, 0)) * price
        position.quantity = new_quantity
        position.avg_price = (current_cost + added_cost) / Decimal(new_quantity)
        position.market_price = price
