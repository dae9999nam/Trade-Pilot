from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GatewayRuntimeStatus(BaseModel):
    platform: str
    python_bits: int
    pywin32_available: bool
    live_trading_enabled: bool
    account_configured: bool
    token_configured: bool
    creon_connected: bool | None = None
    message: str | None = None


class GatewayHealthResponse(BaseModel):
    status: Literal["ok"]
    live_trading_enabled: bool
    runtime: GatewayRuntimeStatus


class GatewayReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    runtime: GatewayRuntimeStatus


class GatewayErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False
    request_id: str | None = None


class QuoteResponse(BaseModel):
    symbol: str
    price: Decimal
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    volume: int | None = None
    source: str = "creon"
    as_of: datetime | None = None


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=16)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: Decimal | None = Field(default=None, ge=0)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @model_validator(mode="after")
    def validate_order_price(self) -> "OrderRequest":
        if self.order_type == "LIMIT" and (self.limit_price is None or self.limit_price <= 0):
            raise ValueError("LIMIT orders require a positive limit_price.")
        return self


class OrderResponse(BaseModel):
    broker_order_id: str | None
    status: str
    message: str
    creon_status_code: int | None = None
    submitted_at: datetime | None = None


class OrderStatusResponse(BaseModel):
    broker_order_id: str | None
    status: str
    message: str
    filled_quantity: int | None = None
    remaining_quantity: int | None = None
    creon_status_code: int | None = None
    as_of: datetime | None = None
    raw_payload: dict | None = None
