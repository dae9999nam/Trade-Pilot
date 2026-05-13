from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker.factory import get_broker
from app.core.auth import authenticate, create_access_token, require_auth
from app.core.config import settings
from app.db.session import get_db
from app.market.data import MarketDataService
from app.models import Order, Position, TradeDecision
from app.schemas import (
    DashboardSummary,
    DecisionListItem,
    DecisionRequest,
    DecisionResponse,
    LoginRequest,
    LoginResponse,
    OrderCreate,
    OrderView,
    PositionView,
    TransactionView,
    UserProfile,
)
from app.services.trading_engine import TradingEngine

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "broker_mode": settings.broker_mode}


@router.get("/config")
def public_config() -> dict[str, object]:
    return {
        "app_env": settings.app_env,
        "broker_mode": settings.broker_mode,
        "auto_execute": settings.auto_execute,
        "live_trading_enabled": settings.live_trading_enabled,
        "openai_model": settings.openai_model,
        "max_order_krw": settings.max_order_krw,
        "max_position_krw": settings.max_position_krw,
        "min_decision_confidence": settings.min_decision_confidence,
    }


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    user = authenticate(payload.username, payload.password)
    return LoginResponse(access_token=create_access_token(user.username), user=user)


@router.get("/auth/me", response_model=UserProfile)
def me(user: UserProfile = Depends(require_auth)) -> UserProfile:
    return user


@router.post("/decisions/run", response_model=DecisionResponse)
def run_decision(payload: DecisionRequest, db: Session = Depends(get_db)) -> DecisionResponse:
    broker = get_broker()
    snapshot = MarketDataService(broker).snapshot_for(payload)
    engine = TradingEngine(db, broker, settings)
    return engine.run_decision(payload, snapshot)


@router.get("/decisions")
def list_decisions(db: Session = Depends(get_db)) -> list[dict[str, object]]:
    rows = db.scalars(select(TradeDecision).order_by(TradeDecision.created_at.desc()).limit(50)).all()
    return [
        {
            "id": row.id,
            "symbol": row.symbol,
            "action": row.action,
            "quantity": row.quantity,
            "confidence": row.confidence,
            "risk_status": row.risk_status,
            "risk_reasons": row.risk_reasons,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> DashboardSummary:
    positions = list(db.scalars(select(Position).order_by(Position.symbol.asc())).all())
    recent_orders = list(db.scalars(select(Order).order_by(Order.created_at.desc()).limit(25)).all())
    recent_decisions = list(
        db.scalars(select(TradeDecision).order_by(TradeDecision.created_at.desc()).limit(10)).all()
    )

    total_market_value = sum(
        (Decimal(position.quantity) * position.market_price for position in positions), Decimal("0")
    )
    total_cost_basis = sum(
        (Decimal(position.quantity) * position.avg_price for position in positions), Decimal("0")
    )
    open_statuses = {"PENDING_APPROVAL", "SUBMITTED"}

    return DashboardSummary(
        user=user,
        broker_mode=settings.broker_mode,
        live_trading_enabled=settings.live_trading_enabled,
        auto_execute=settings.auto_execute,
        total_market_value=total_market_value,
        total_cost_basis=total_cost_basis,
        unrealized_pnl=total_market_value - total_cost_basis,
        positions_count=sum(1 for position in positions if position.quantity != 0),
        open_orders_count=sum(1 for order in recent_orders if order.status in open_statuses),
        filled_orders_count=sum(1 for order in recent_orders if order.status == "FILLED"),
        rejected_orders_count=sum(1 for order in recent_orders if order.status == "REJECTED"),
        recent_transactions=[_transaction_view(order) for order in recent_orders],
        positions=positions,
        recent_decisions=[_decision_view(decision) for decision in recent_decisions],
    )


@router.get("/dashboard/transactions", response_model=list[TransactionView])
def dashboard_transactions(
    db: Session = Depends(get_db),
    _: UserProfile = Depends(require_auth),
) -> list[TransactionView]:
    orders = db.scalars(select(Order).order_by(Order.created_at.desc()).limit(100)).all()
    return [_transaction_view(order) for order in orders]


@router.post("/orders", response_model=OrderView)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)) -> Order:
    return TradingEngine(db, get_broker(), settings).create_manual_order(payload)


@router.post("/orders/{order_id}/approve", response_model=OrderView)
def approve_order(order_id: int, db: Session = Depends(get_db)) -> Order:
    try:
        return TradingEngine(db, get_broker(), settings).approve_order(order_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/orders", response_model=list[OrderView])
def list_orders(db: Session = Depends(get_db)) -> list[Order]:
    return list(db.scalars(select(Order).order_by(Order.created_at.desc()).limit(50)).all())


@router.get("/positions", response_model=list[PositionView])
def list_positions(db: Session = Depends(get_db)) -> list[Position]:
    return list(db.scalars(select(Position).order_by(Position.symbol.asc())).all())


def _transaction_view(order: Order) -> TransactionView:
    return TransactionView(
        id=order.id,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        order_type=order.order_type,
        limit_price=order.limit_price,
        status=order.status,
        mode=order.mode,
        broker_order_id=order.broker_order_id,
        message=order.message,
        created_at=order.created_at.isoformat(),
    )


def _decision_view(decision: TradeDecision) -> DecisionListItem:
    return DecisionListItem(
        id=decision.id,
        symbol=decision.symbol,
        action=decision.action,
        quantity=decision.quantity,
        confidence=decision.confidence,
        risk_status=decision.risk_status,
        risk_reasons=decision.risk_reasons,
        created_at=decision.created_at.isoformat(),
    )
