from fastapi import Depends, FastAPI, Header, HTTPException

from config import settings
from creon_client import CreonClient
from schemas import OrderRequest, OrderResponse, QuoteResponse

app = FastAPI(title="Trade-pilot CREON Gateway", version="0.1.0")


def require_token(x_trade_pilot_token: str | None = Header(default=None)) -> None:
    if settings.gateway_token and x_trade_pilot_token != settings.gateway_token:
        raise HTTPException(status_code=401, detail="Invalid gateway token.")


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "live_trading_enabled": settings.live_trading_enabled}


@app.get("/quote/{symbol}", response_model=QuoteResponse, dependencies=[Depends(require_token)])
def quote(symbol: str) -> QuoteResponse:
    try:
        return CreonClient().quote(symbol.upper())
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/orders", response_model=OrderResponse, dependencies=[Depends(require_token)])
def orders(payload: OrderRequest) -> OrderResponse:
    try:
        return CreonClient().order(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
