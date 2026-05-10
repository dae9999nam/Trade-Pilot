from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

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


class Broker(ABC):
    name: str

    @abstractmethod
    def get_quote(self, symbol: str) -> MarketSnapshot:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        raise NotImplementedError

