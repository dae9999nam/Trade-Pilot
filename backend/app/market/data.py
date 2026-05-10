from decimal import Decimal

from app.broker.base import Broker
from app.schemas import DecisionRequest, MarketSnapshot


class MarketDataService:
    def __init__(self, broker: Broker) -> None:
        self.broker = broker

    def snapshot_for(self, request: DecisionRequest) -> MarketSnapshot:
        if request.last_price is not None:
            return MarketSnapshot(
                symbol=request.symbol.upper(),
                price=Decimal(request.last_price),
                source="request",
            )
        return self.broker.get_quote(request.symbol.upper())

