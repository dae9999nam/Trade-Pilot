from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker.factory import get_broker
from app.core.config import settings
from app.db.session import get_db
from app.market.data import MarketDataService
from app.models import Order, Position, TradeDecision
from app.schemas import DecisionRequest, DecisionResponse, OrderCreate, OrderView, PositionView
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

