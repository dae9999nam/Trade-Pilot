from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.broker.base import Broker, BrokerOrder, BrokerOrderResult
from app.broker.paper import PaperBroker
from app.core.config import Settings
from app.db.base import Base
from app.models import OrderEvent, Position
from app.schemas import MarketSnapshot, OrderCreate
from app.services.order_lifecycle import (
    ORDER_FILLED,
    ORDER_PENDING_APPROVAL,
    ORDER_SUBMISSION_FAILED,
    can_approve,
    is_terminal,
)
from app.services.trading_engine import TradingEngine


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

    approved_order = engine.approve_order(order.id)
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
        "order_approved",
        "broker_submit_started",
        "broker_submit_result",
    ]


def test_broker_submission_failure_remains_approvable_for_retry() -> None:
    db = _session()
    engine = TradingEngine(
        db,
        FailingBroker(),
        Settings(openai_api_key=None, broker_mode="creon_gateway"),
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

    failed_order = engine.approve_order(order.id)
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


class FailingBroker(Broker):
    name = "failing"

    def get_quote(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(symbol=symbol, price=Decimal("1"), source=self.name)

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise RuntimeError("gateway unavailable")
