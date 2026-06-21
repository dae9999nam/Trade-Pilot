from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from app.broker.base import Broker, BrokerOrder, BrokerOrderResult, BrokerOrderStatusResult
from app.schemas import MarketSnapshot


class PaperBroker(Broker):
    name = "paper"

    def get_quote(self, symbol: str) -> MarketSnapshot:
        seed = int(sha256(symbol.encode("utf-8")).hexdigest()[:8], 16)
        base = Decimal(50_000 + seed % 120_000)
        return MarketSnapshot(
            symbol=symbol.upper(),
            price=base,
            open_price=base * Decimal("0.992"),
            high_price=base * Decimal("1.018"),
            low_price=base * Decimal("0.981"),
            volume=1_000_000 + seed % 500_000,
            source=self.name,
        )

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        return BrokerOrderResult(
            broker_order_id=f"PAPER-{uuid4().hex[:12].upper()}",
            status="FILLED",
            message="Paper order filled immediately.",
        )

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatusResult:
        normalized = broker_order_id.upper()
        if normalized.startswith("DEMO-SUB"):
            return BrokerOrderStatusResult(
                broker_order_id=broker_order_id,
                status="SUBMITTED",
                message="Demo paper order remains submitted.",
                as_of=datetime.now(UTC),
            )
        if normalized.startswith("DEMO-FILL") or normalized.startswith("PAPER-"):
            return BrokerOrderStatusResult(
                broker_order_id=broker_order_id,
                status="FILLED",
                message="Paper order is filled.",
                as_of=datetime.now(UTC),
            )
        return BrokerOrderStatusResult(
            broker_order_id=broker_order_id,
            status="SUBMITTED",
            message="Paper broker has no external order book; preserving submitted state.",
            as_of=datetime.now(UTC),
        )

    def cancel_order(self, broker_order_id: str) -> BrokerOrderStatusResult:
        return BrokerOrderStatusResult(
            broker_order_id=broker_order_id,
            status="CANCELED",
            message="Paper order canceled.",
            as_of=datetime.now(UTC),
        )
