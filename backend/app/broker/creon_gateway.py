from datetime import datetime
from decimal import Decimal

import httpx

from app.broker.base import (
    Broker,
    BrokerAccountPosition,
    BrokerAccountSnapshot,
    BrokerOrder,
    BrokerOrderResult,
    BrokerOrderStatusResult,
)
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
        return {"x-trade-pilot-token": self.settings.creon_gateway_token}

    def get_quote(self, symbol: str) -> MarketSnapshot:
        response = self.client.get(f"/quote/{symbol}")
        self._raise_for_gateway_error(response)
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
        self._raise_for_gateway_error(response)
        data = response.json()
        return BrokerOrderResult(
            broker_order_id=data.get("broker_order_id"),
            status=data["status"],
            message=data["message"],
        )

    def get_order_status(self, broker_order_id: str) -> BrokerOrderStatusResult:
        response = self.client.get(f"/orders/{broker_order_id}")
        self._raise_for_gateway_error(response)
        data = response.json()
        return BrokerOrderStatusResult(
            broker_order_id=data.get("broker_order_id"),
            status=data["status"],
            message=data["message"],
            filled_quantity=data.get("filled_quantity"),
            remaining_quantity=data.get("remaining_quantity"),
            as_of=data.get("as_of"),
            raw_payload=data.get("raw_payload"),
        )

    def cancel_order(self, broker_order_id: str) -> BrokerOrderStatusResult:
        response = self.client.post(f"/orders/{broker_order_id}/cancel")
        self._raise_for_gateway_error(response)
        data = response.json()
        return BrokerOrderStatusResult(
            broker_order_id=data.get("broker_order_id"),
            status=data["status"],
            message=data["message"],
            filled_quantity=data.get("filled_quantity"),
            remaining_quantity=data.get("remaining_quantity"),
            as_of=data.get("as_of"),
            raw_payload=data.get("raw_payload"),
        )

    def get_account_snapshot(self) -> BrokerAccountSnapshot:
        response = self.client.get("/account")
        self._raise_for_gateway_error(response)
        data = response.json()
        return BrokerAccountSnapshot(
            source=data.get("source", self.name),
            cash_krw=Decimal(str(data["cash_krw"])) if data.get("cash_krw") is not None else None,
            positions=[
                BrokerAccountPosition(
                    symbol=item["symbol"],
                    quantity=int(item["quantity"]),
                    avg_price=Decimal(str(item["avg_price"])) if item.get("avg_price") is not None else None,
                    market_price=(
                        Decimal(str(item["market_price"])) if item.get("market_price") is not None else None
                    ),
                    raw_payload=item.get("raw_payload"),
                )
                for item in data.get("positions", [])
            ],
            as_of=self._parse_datetime(data.get("as_of")),
            raw_payload=data.get("raw_payload"),
        )

    def _parse_datetime(self, value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _raise_for_gateway_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()

        detail = payload.get("detail") if isinstance(payload, dict) else None
        if isinstance(detail, dict):
            code = detail.get("code", "creon_gateway_error")
            message = detail.get("message", response.text)
            request_id = detail.get("request_id")
            suffix = f" request_id={request_id}" if request_id else ""
            raise RuntimeError(f"CREON gateway {code}: {message}{suffix}")
        if isinstance(detail, str):
            raise RuntimeError(f"CREON gateway error: {detail}")
        response.raise_for_status()
