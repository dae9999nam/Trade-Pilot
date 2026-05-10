from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class QuoteResponse(BaseModel):
    symbol: str
    price: Decimal
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    volume: int | None = None


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=2, max_length=16)
    side: Literal["BUY", "SELL"]
    quantity: int = Field(gt=0)
    order_type: Literal["MARKET", "LIMIT"]
    limit_price: Decimal | None = Field(default=None, ge=0)


class OrderResponse(BaseModel):
    broker_order_id: str | None
    status: str
    message: str

