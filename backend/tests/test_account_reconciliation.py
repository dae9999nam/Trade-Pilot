from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.broker.base import (
    Broker,
    BrokerAccountPosition,
    BrokerAccountSnapshot,
    BrokerOrder,
    BrokerOrderResult,
)
from app.broker.paper import PaperBroker
from app.core.config import Settings
from app.db.base import Base
from app.models import Position
from app.schemas import MarketSnapshot
from app.services.account_reconciliation import AccountReconciliationService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_position(
    db: Session,
    *,
    symbol: str,
    quantity: int,
    avg_price: str = "70000",
    market_price: str = "71000",
) -> None:
    db.add(
        Position(
            user_id=1,
            symbol=symbol,
            quantity=quantity,
            avg_price=Decimal(avg_price),
            market_price=Decimal(market_price),
        )
    )
    db.flush()


def test_paper_reconciliation_uses_app_database_as_ledger() -> None:
    db = _session()
    _add_position(db, symbol="A005930", quantity=3)

    response = AccountReconciliationService(
        db,
        PaperBroker(),
        Settings(openai_api_key=None, broker_mode="paper"),
        user_id=1,
    ).run()

    assert response.broker_status == "PAPER"
    assert response.rows[0].symbol == "A005930"
    assert response.rows[0].status == "MATCHED"
    assert response.rows[0].broker_quantity == 3


def test_live_reconciliation_detects_missing_and_quantity_mismatch() -> None:
    db = _session()
    _add_position(db, symbol="A005930", quantity=3)
    broker = SnapshotBroker(
        BrokerAccountSnapshot(
            source="test_broker",
            positions=[
                BrokerAccountPosition(symbol="A005930", quantity=2, market_price=Decimal("72000")),
                BrokerAccountPosition(symbol="A000660", quantity=4, market_price=Decimal("130000")),
            ],
        )
    )

    response = AccountReconciliationService(
        db,
        broker,
        Settings(openai_api_key=None, broker_mode="creon_gateway"),
        user_id=1,
    ).run()

    statuses = {row.symbol: row.status for row in response.rows}
    assert response.broker_status == "SYNCED"
    assert statuses == {
        "A000660": "MISSING_IN_APP",
        "A005930": "QUANTITY_MISMATCH",
    }


def test_live_reconciliation_surfaces_broker_unavailable() -> None:
    db = _session()
    _add_position(db, symbol="A005930", quantity=3)

    response = AccountReconciliationService(
        db,
        UnavailableBroker(),
        Settings(openai_api_key=None, broker_mode="creon_gateway"),
        user_id=1,
    ).run()

    assert response.broker_status == "UNAVAILABLE"
    assert response.rows[0].status == "BROKER_UNAVAILABLE"
    assert "gateway down" in response.message


class SnapshotBroker(Broker):
    name = "snapshot"

    def __init__(self, snapshot: BrokerAccountSnapshot) -> None:
        self.snapshot = snapshot

    def get_quote(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(symbol=symbol, price=Decimal("1"), source=self.name)

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        return BrokerOrderResult(broker_order_id=None, status="REJECTED", message="not used")

    def get_account_snapshot(self) -> BrokerAccountSnapshot:
        return self.snapshot


class UnavailableBroker(Broker):
    name = "unavailable"

    def get_quote(self, symbol: str) -> MarketSnapshot:
        return MarketSnapshot(symbol=symbol, price=Decimal("1"), source=self.name)

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        return BrokerOrderResult(broker_order_id=None, status="REJECTED", message="not used")

    def get_account_snapshot(self) -> BrokerAccountSnapshot:
        raise RuntimeError("gateway down")
