from decimal import Decimal

import httpx

from app.broker.base import Broker, BrokerOrder, BrokerOrderResult
from app.core.config import Settings
from app.schemas import MarketSnapshot


class CreonGatewayBroker(Broker):
    name = "creon_gateway"

    def __init__(self, settings: Settings) -> None:
        if not settings.live_trading_enabled:
            raise RuntimeError("CREON gateway mode requires explicit live trading approvals.")
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.creon_gateway_url.rstrip("/"),
            timeout=settings.creon_gateway_timeout_seconds,
            headers=self._headers(),
        )

    def _headers(self) -> dict[str, str]:
        if not self.settings.creon_gateway_token:
            return {}
        return {"x-stock-pilot-token": self.settings.creon_gateway_token}

    def get_quote(self, symbol: str) -> MarketSnapshot:
        response = self.client.get(f"/quote/{symbol}")
        response.raise_for_status()
        data = response.json()
        return MarketSnapshot(
            symbol=data["symbol"],
            price=Decimal(str(data["price"])),
            open_price=Decimal(str(data["open_price"])) if data.get("open_price") else None,
            high_price=Decimal(str(data["high_price"])) if data.get("high_price") else None,
            low_price=Decimal(str(data["low_price"])) if data.get("low_price") else None,
            volume=data.get("volume"),
            source=self.name,
        )

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        response = self.client.post(
            "/orders",
            json={
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "order_type": order.order_type,
                "limit_price": str(order.limit_price) if order.limit_price is not None else None,
            },
        )
        response.raise_for_status()
        data = response.json()
        return BrokerOrderResult(
            broker_order_id=data.get("broker_order_id"),
            status=data["status"],
            message=data["message"],
        )

