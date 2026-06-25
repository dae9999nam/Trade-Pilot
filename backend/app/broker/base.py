from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from app.schemas import MarketSnapshot


@dataclass(frozen=True)
class BrokerOrder:
    symbol: str
    side: Literal["BUY", "SELL"]
    quantity: int
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: Decimal | None


@dataclass(frozen=True)
class BrokerOrderResult:
    broker_order_id: str | None
    status: str
    message: str


@dataclass(frozen=True)
class BrokerOrderStatusResult:
    broker_order_id: str | None
    status: str
    message: str
    filled_quantity: int | None = None
    remaining_quantity: int | None = None
    as_of: datetime | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class BrokerAccountPosition:
    symbol: str
    quantity: int
    avg_price: Decimal | None = None
    market_price: Decimal | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class BrokerAccountSnapshot:
    source: str
    cash_krw: Decimal | None = None
    positions: list[BrokerAccountPosition] = field(default_factory=list)
    as_of: datetime | None = None
    raw_payload: dict[str, Any] | None = None


class Broker(ABC):
    name: str

    @abstractmethod
    def get_quote(self, symbol: str) -> MarketSnapshot:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise NotImplementedError

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatusResult:
        raise NotImplementedError(f"{self.name} broker does not support order status refresh.")

    def cancel_order(self, broker_order_id: str) -> BrokerOrderStatusResult:
        raise NotImplementedError(f"{self.name} broker does not support order cancellation.")

    def get_account_snapshot(self) -> BrokerAccountSnapshot:
        raise NotImplementedError(f"{self.name} broker does not support account snapshots.")
