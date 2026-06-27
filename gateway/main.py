import hmac
import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse

from config import settings
from creon_client import CreonClient, CreonGatewayError
from schemas import (
    AccountSnapshotResponse,
    GatewayErrorDetail,
    GatewayHealthResponse,
    GatewayReadinessResponse,
    OrderRequest,
    OrderResponse,
    OrderStatusResponse,
    QuoteResponse,
)

logger = logging.getLogger("trade_pilot.creon_gateway")

app = FastAPI(title="Trade-pilot CREON Gateway", version="0.3.0")
client = CreonClient()


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(CreonGatewayError)
async def creon_gateway_error_handler(request: Request, exc: CreonGatewayError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.warning("CREON gateway error request_id=%s code=%s message=%s", request_id, exc.code, exc)
    detail = GatewayErrorDetail(
        code=exc.code,
        message=str(exc),
        retryable=exc.retryable,
        request_id=request_id,
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": detail.model_dump()})


def require_token(x_trade_pilot_token: str | None = Header(default=None)) -> None:
    if settings.live_trading_enabled and not settings.gateway_token:
        raise HTTPException(status_code=503, detail="GATEWAY_TOKEN is required when live trading is enabled.")
    if not settings.gateway_token:
        return
    if x_trade_pilot_token is None:
        raise HTTPException(status_code=401, detail="Missing gateway token.")
    if not hmac.compare_digest(x_trade_pilot_token, settings.gateway_token):
        raise HTTPException(status_code=401, detail="Invalid gateway token.")


@app.get("/health", response_model=GatewayHealthResponse)
def health() -> GatewayHealthResponse:
    return GatewayHealthResponse(
        status="ok",
        live_trading_enabled=settings.live_trading_enabled,
        runtime=client.runtime_status(check_creon_connection=False),
    )


@app.get("/ready", response_model=GatewayReadinessResponse)
def ready(response: Response) -> GatewayReadinessResponse:
    runtime = client.readiness()
    is_ready = (
        runtime.platform == "Windows"
        and runtime.python_bits == 32
        and runtime.pywin32_available
        and runtime.live_trading_enabled
        and runtime.account_configured
        and runtime.token_configured
        and runtime.creon_connected is True
    )
    if not is_ready:
        response.status_code = 503
    return GatewayReadinessResponse(status="ready" if is_ready else "not_ready", runtime=runtime)


@app.get("/quote/{symbol}", response_model=QuoteResponse, dependencies=[Depends(require_token)])
def quote(symbol: str = Path(min_length=2, max_length=16)) -> QuoteResponse:
    return client.quote(symbol)


@app.get("/account", response_model=AccountSnapshotResponse, dependencies=[Depends(require_token)])
def account() -> AccountSnapshotResponse:
    return client.account_snapshot()


@app.post("/orders", response_model=OrderResponse, dependencies=[Depends(require_token)])
def orders(payload: OrderRequest) -> OrderResponse:
    return client.order(payload)


@app.get("/orders/{broker_order_id}", response_model=OrderStatusResponse, dependencies=[Depends(require_token)])
def order_status(broker_order_id: str = Path(min_length=1, max_length=64)) -> OrderStatusResponse:
    return client.order_status(broker_order_id)


@app.post("/orders/{broker_order_id}/cancel", response_model=OrderStatusResponse, dependencies=[Depends(require_token)])
def cancel_order(broker_order_id: str = Path(min_length=1, max_length=64)) -> OrderStatusResponse:
    return client.cancel_order(broker_order_id)
