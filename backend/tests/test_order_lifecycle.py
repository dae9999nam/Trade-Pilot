from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.broker.base import Broker, BrokerOrder, BrokerOrderResult, BrokerOrderStatusResult
from app.broker.paper import PaperBroker
from app.core.config import Settings
from app.db.base import Base
from app.models import OrderEvent, Position, UserTradingSettings
from app.schemas import MarketSnapshot, OrderCreate
from app.services.order_lifecycle import (
    ORDER_FILLED,
    ORDER_CANCELED,
    ORDER_PENDING_APPROVAL,
    ORDER_REJECTED,
    ORDER_SUBMITTED,
    ORDER_SUBMISSION_FAILED,
    can_approve,
    can_cancel,
    is_terminal,
)
from app.services.trading_engine import OrderApprovalConfirmationError, TradingEngine


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_manual_order_lifecycle_fills_paper_order() -> None:
    db = _session()
    engine = TradingEngine(
        db,
        PaperBroker(),
        Settings(openai_api_key=None, broker_mode="paper"),
        user_id=1,
    )

    order = engine.create_manual_order(
        OrderCreate(
            symbol="A005930",
            side="BUY",
            quantity=3,
            order_type="LIMIT",
            limit_price=Decimal("70000"),
        )
    )

    assert order.status == ORDER_PENDING_APPROVAL
    assert can_approve(order)
    assert order.submission_attempts == 0

    preview = engine.preview_order_approval(order.id)
    approved_order = engine.approve_order(order.id, preview.confirmation_text)
    position = db.scalar(select(Position).where(Position.symbol == "A005930"))
    events = db.scalars(
        select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.id.asc())
    ).all()

    assert approved_order.status == ORDER_FILLED
    assert approved_order.submission_attempts == 1
    assert approved_order.approved_at is not None
    assert approved_order.submitted_at is not None
    assert approved_order.filled_at is not None
    assert approved_order.broker_order_id is not None
    assert is_terminal(approved_order)
    assert not can_approve(approved_order)
    assert position is not None
    assert position.quantity == 3
    assert [event.event_type for event in events] == [
        "manual_order_staged",
        "order_approval_previewed",
        "order_approved",
        "broker_submit_started",
        "broker_submit_result",
    ]
    assert events[1].event_payload is not None
    assert events[1].event_payload["estimated_notional_krw"] == "210000.00"


def test_broker_submission_failure_remains_approvable_for_retry() -> None:
    db = _session()
    db.add(
        UserTradingSettings(
            user_id=1,
            max_order_krw=500000,
            max_position_krw=1000000,
            min_decision_confidence=0.62,
            require_manual_approval=True,
            live_trading_opt_in=True,
        )
    )
    db.flush()
    engine = TradingEngine(
        db,
        FailingBroker(),
        Settings(
            openai_api_key=None,
            broker_mode="creon_gateway",
            allow_live_trading=True,
            i_understand_loss_risk=True,
        ),
        user_id=1,
    )
    order = engine.create_manual_order(
        OrderCreate(
            symbol="A005930",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            limit_price=Decimal("70000"),
        )
    )

    preview = engine.preview_order_approval(order.id)
    failed_order = engine.approve_order(order.id, preview.confirmation_text)
    failure_events = db.scalars(
        select(OrderEvent)
        .where(OrderEvent.order_id == order.id, OrderEvent.event_type == "broker_submit_failed")
    ).all()

    assert failed_order.status == ORDER_SUBMISSION_FAILED
    assert failed_order.submission_attempts == 1
    assert failed_order.failed_at is not None
    assert can_approve(failed_order)
    assert not is_terminal(failed_order)
    assert failure_events
    assert failure_events[0].event_payload == {"exception_type": "RuntimeError"}


def test_live_gateway_order_requires_user_opt_in() -> None:
    db = _session()
    engine = TradingEngine(
        db,
        FailingBroker(),
        Settings(
            openai_api_key=None,
            broker_mode="creon_gateway",
            allow_live_trading=True,
            i_understand_loss_risk=True,
        ),
        user_id=1,
    )
    order = engine.create_manual_order(
        OrderCreate(
            symbol="A005930",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            limit_price=Decimal("70000"),
        )
    )

    preview = engine.preview_order_approval(order.id)
    rejected_order = engine.approve_order(order.id, preview.confirmation_text)
    safety_events = db.scalars(
        select(OrderEvent).where(OrderEvent.order_id == order.id, OrderEvent.event_type == "order_rejected_by_safety")
    ).all()

    assert rejected_order.status == ORDER_REJECTED
    assert rejected_order.rejected_at is not None
    assert safety_events
    assert safety_events[0].message == "User live trading opt-in is disabled."


def test_order_approval_requires_confirmation_text() -> None:
    db = _session()
    engine = TradingEngine(
        db,
        PaperBroker(),
        Settings(openai_api_key=None, broker_mode="paper"),
        user_id=1,
    )
    order = engine.create_manual_order(
        OrderCreate(
            symbol="A005930",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            limit_price=Decimal("70000"),
        )
    )

    preview = engine.preview_order_approval(order.id)
    try:
        engine.approve_order(order.id, "APPROVE WRONG")
    except OrderApprovalConfirmationError:
        pass
    else:
        raise AssertionError("Expected confirmation failure.")

    failed_events = db.scalars(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id,
            OrderEvent.event_type == "order_approval_confirmation_failed",
        )
    ).all()

    assert preview.confirmation_text == f"APPROVE {order.id}"
    assert failed_events
    assert order.status == ORDER_PENDING_APPROVAL


def test_pending_order_can_be_canceled_locally() -> None:
    db = _session()
    engine = TradingEngine(
        db,
        PaperBroker(),
        Settings(openai_api_key=None, broker_mode="paper"),
        user_id=1,
    )
    order = engine.create_manual_order(
        OrderCreate(
            symbol="A005930",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
            limit_price=Decimal("70000"),
        )
    )

    canceled_order = engine.cancel_order(order.id)
    cancel_events = db.scalars(
        select(OrderEvent).where(OrderEvent.order_id == order.id, OrderEvent.event_type == "order_canceled")
    ).all()

    assert canceled_order.status == ORDER_CANCELED
    assert canceled_order.canceled_at is not None
    assert is_terminal(canceled_order)
    assert not can_cancel(canceled_order)
    assert cancel_events


def test_refresh_submitted_order_can_fill_and_update_paper_position() -> None:
    db = _session()
    engine = TradingEngine(
        db,
        SubmittedThenFilledBroker(),
        Settings(openai_api_key=None, broker_mode="paper"),
        user_id=1,
    )
    order = engine.create_manual_order(
        OrderCreate(
            symbol="A005930",
            side="BUY",
            quantity=2,
            order_type="LIMIT",
            limit_price=Decimal("70000"),
        )
    )

    preview = engine.preview_order_approval(order.id)
    submitted_order = engine.approve_order(order.id, preview.confirmation_text)
    assert submitted_order.status == ORDER_SUBMITTED
    assert db.scalar(select(Position).where(Position.symbol == "A005930")) is None

    refreshed_order = engine.refresh_order_status(order.id)
    position = db.scalar(select(Position).where(Position.symbol == "A005930"))
    refresh_events = db.scalars(
        select(OrderEvent).where(
            OrderEvent.order_id == order.id,
            OrderEvent.event_type == "broker_status_refreshed",
        )
    ).all()

    assert refreshed_order.status == ORDER_FILLED
    assert refreshed_order.filled_at is not None
    assert position is not None
    assert position.quantity == 2
    assert refresh_events
    assert refresh_events[0].event_payload is not None
    assert refresh_events[0].event_payload["filled_quantity"] == 2
    assert refresh_events[0].event_payload["remaining_quantity"] == 0
    assert refresh_events[0].event_payload["as_of"] == "2026-06-27T01:02:03+00:00"


class FailingBroker(Broker):
    name = "failing"

    def get_quote(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(symbol=symbol, price=Decimal("1"), source=self.name)

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise RuntimeError("gateway unavailable")


class SubmittedThenFilledBroker(Broker):
    name = "submitted_then_filled"

    def get_quote(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(symbol=symbol, price=Decimal("70000"), source=self.name)

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        return BrokerOrderResult(
            broker_order_id="BROKER-SUBMITTED-1",
            status="SUBMITTED",
            message="Accepted by test broker.",
        )

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatusResult:
        return BrokerOrderStatusResult(
            broker_order_id=broker_order_id,
            status="FILLED",
            message="Filled by test broker.",
            filled_quantity=2,
            remaining_quantity=0,
            as_of=datetime(2026, 6, 27, 1, 2, 3, tzinfo=UTC),
        )
