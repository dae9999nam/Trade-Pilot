from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker.factory import get_broker
from app.core.auth import (
    authenticate,
    create_authenticated_session,
    hash_password,
    logout_current_session,
    require_admin,
    register_user,
    require_auth,
    verify_password,
)
from app.core.config import settings
from app.db.session import get_db
from app.market.data import MarketDataService
from app.models import Order, OrderEvent, Position, TradeDecision, User, UserSession
from app.schemas import (
    AccountReconciliationResponse,
    AssistantQueryRequest,
    AssistantQueryResponse,
    DashboardSummary,
    DecisionListItem,
    DecisionRequest,
    DecisionResponse,
    LoginRequest,
    LoginResponse,
    OrderApprovalPreview,
    OrderApprovalRequest,
    OrderCreate,
    OrderEventView,
    OrderView,
    PositionView,
    RegisterRequest,
    TransactionView,
    TradingSafetySettingsResponse,
    TradingSafetySettingsUpdate,
    UserProfile,
    UserProfileUpdate,
)
from app.services.account_reconciliation import AccountReconciliationService
from app.services.assistant_workspace import AssistantWorkspace
from app.services.order_lifecycle import (
    ORDER_FILLED,
    ORDER_OPEN_STATUSES,
    ORDER_REJECTED,
    can_approve,
    can_cancel,
    is_terminal,
)
from app.services.trading_engine import (
    OrderApprovalConfirmationError,
    OrderNotFoundError,
    TradingEngine,
)
from app.services.trading_safety import (
    get_or_create_user_trading_settings,
    safety_response,
    update_user_trading_settings,
)

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


@router.post("/auth/register", response_model=LoginResponse)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    if not settings.allow_user_registration:
        raise HTTPException(status_code=403, detail="User registration is disabled.")
    user = register_user(db, payload.email, payload.password)
    return create_authenticated_session(db, user, response, request)


@router.post("/auth/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    user = authenticate(db, payload.username, payload.password)
    return create_authenticated_session(db, user, response, request)


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _: UserProfile = Depends(require_auth),
) -> dict[str, bool]:
    return logout_current_session(db, request, response)


@router.get("/auth/me", response_model=UserProfile)
def me(user: UserProfile = Depends(require_auth)) -> UserProfile:
    return user


@router.patch("/auth/me", response_model=UserProfile)
def update_me(
    payload: UserProfileUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> UserProfile:
    user_row = db.get(User, user.id)
    if user_row is None or not user_row.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    if not verify_password(payload.current_password, user_row.password_hash):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")

    changed = False
    if payload.email and payload.email != user_row.email:
        existing_user_id = db.scalar(select(User.id).where(User.email == payload.email))
        if existing_user_id is not None and existing_user_id != user_row.id:
            raise HTTPException(status_code=409, detail="User already exists.")
        user_row.email = payload.email
        changed = True

    if payload.new_password:
        user_row.password_hash = hash_password(payload.new_password)
        _revoke_other_sessions(db, request, user_row.id)
        changed = True

    if changed:
        db.commit()
        db.refresh(user_row)
    return UserProfile(id=user_row.id, username=user_row.email, email=user_row.email, role=user_row.role)  # type: ignore[arg-type]


@router.get("/settings/trading-safety", response_model=TradingSafetySettingsResponse)
def get_trading_safety_settings(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> TradingSafetySettingsResponse:
    row = get_or_create_user_trading_settings(db, user.id, settings)
    db.commit()
    db.refresh(row)
    return safety_response(row, settings)


@router.patch("/settings/trading-safety", response_model=TradingSafetySettingsResponse)
def update_trading_safety_settings(
    payload: TradingSafetySettingsUpdate,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> TradingSafetySettingsResponse:
    row = get_or_create_user_trading_settings(db, user.id, settings)
    update_user_trading_settings(row, payload, settings)
    db.commit()
    db.refresh(row)
    return safety_response(row, settings)


@router.post("/decisions/run", response_model=DecisionResponse)
def run_decision(
    payload: DecisionRequest,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> DecisionResponse:
    broker = get_broker()
    snapshot = MarketDataService(broker).snapshot_for(payload)
    engine = TradingEngine(db, broker, settings, user.id)
    return engine.run_decision(payload, snapshot)


@router.post("/assistant/query", response_model=AssistantQueryResponse)
def run_assistant_query(
    payload: AssistantQueryRequest,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> AssistantQueryResponse:
    return AssistantWorkspace(db, get_broker(), settings, user.id).run(payload)


@router.get("/decisions")
def list_decisions(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> list[dict[str, object]]:
    rows = db.scalars(
        select(TradeDecision)
        .where(TradeDecision.user_id == user.id)
        .order_by(TradeDecision.created_at.desc())
        .limit(50)
    ).all()
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
    user: UserProfile = Depends(require_admin),
) -> DashboardSummary:
    positions = list(
        db.scalars(select(Position).where(Position.user_id == user.id).order_by(Position.symbol.asc())).all()
    )
    recent_orders = list(
        db.scalars(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(25)
        ).all()
    )
    recent_decisions = list(
        db.scalars(
            select(TradeDecision)
            .where(TradeDecision.user_id == user.id)
            .order_by(TradeDecision.created_at.desc())
            .limit(10)
        ).all()
    )

    total_market_value = sum(
        (Decimal(position.quantity) * position.market_price for position in positions), Decimal("0")
    )
    total_cost_basis = sum(
        (Decimal(position.quantity) * position.avg_price for position in positions), Decimal("0")
    )
    return DashboardSummary(
        user=user,
        broker_mode=settings.broker_mode,
        live_trading_enabled=settings.live_trading_enabled,
        auto_execute=settings.auto_execute,
        total_market_value=total_market_value,
        total_cost_basis=total_cost_basis,
        unrealized_pnl=total_market_value - total_cost_basis,
        positions_count=sum(1 for position in positions if position.quantity != 0),
        open_orders_count=sum(1 for order in recent_orders if order.status in ORDER_OPEN_STATUSES),
        filled_orders_count=sum(1 for order in recent_orders if order.status == ORDER_FILLED),
        rejected_orders_count=sum(1 for order in recent_orders if order.status == ORDER_REJECTED),
        recent_transactions=[_transaction_view(order) for order in recent_orders],
        positions=positions,
        recent_decisions=[_decision_view(decision) for decision in recent_decisions],
    )


@router.get("/dashboard/transactions", response_model=list[TransactionView])
def dashboard_transactions(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_admin),
) -> list[TransactionView]:
    orders = db.scalars(
        select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(100)
    ).all()
    return [_transaction_view(order) for order in orders]


@router.post("/orders", response_model=OrderView)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_admin),
) -> OrderView:
    order = TradingEngine(db, get_broker(), settings, user.id).create_manual_order(payload)
    return _order_view(order)


@router.post("/orders/{order_id}/approval-preview", response_model=OrderApprovalPreview)
def preview_order_approval(
    order_id: int,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> OrderApprovalPreview:
    try:
        return TradingEngine(db, get_broker(), settings, user.id).preview_order_approval(order_id)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/orders/{order_id}/approve", response_model=OrderView)
def approve_order(
    order_id: int,
    payload: OrderApprovalRequest,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> OrderView:
    try:
        order = TradingEngine(db, get_broker(), settings, user.id).approve_order(
            order_id,
            payload.confirmation_text,
        )
        return _order_view(order)
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OrderApprovalConfirmationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/orders/{order_id}/cancel", response_model=OrderView)
def cancel_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> OrderView:
    try:
        order = TradingEngine(db, get_broker(), settings, user.id).cancel_order(order_id)
        return _order_view(order)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/orders/{order_id}/refresh", response_model=OrderView)
def refresh_order_status(
    order_id: int,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> OrderView:
    try:
        order = TradingEngine(db, get_broker(), settings, user.id).refresh_order_status(order_id)
        return _order_view(order)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/orders", response_model=list[OrderView])
def list_orders(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> list[OrderView]:
    return [
        _order_view(order)
        for order in db.scalars(
            select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(50)
        ).all()
    ]


@router.get("/orders/{order_id}/events", response_model=list[OrderEventView])
def list_order_events(
    order_id: int,
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> list[OrderEvent]:
    order = db.scalar(select(Order).where(Order.id == order_id, Order.user_id == user.id))
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")
    return list(
        db.scalars(
            select(OrderEvent)
            .where(OrderEvent.order_id == order_id)
            .order_by(OrderEvent.created_at.asc(), OrderEvent.id.asc())
        ).all()
    )


@router.get("/positions", response_model=list[PositionView])
def list_positions(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> list[Position]:
    return list(
        db.scalars(select(Position).where(Position.user_id == user.id).order_by(Position.symbol.asc())).all()
    )


@router.get("/account/reconciliation", response_model=AccountReconciliationResponse)
def account_reconciliation(
    db: Session = Depends(get_db),
    user: UserProfile = Depends(require_auth),
) -> AccountReconciliationResponse:
    return AccountReconciliationService(db, get_broker(), settings, user.id).run()


def _order_view(order: Order) -> OrderView:
    return OrderView(
        id=order.id,
        mode=order.mode,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        order_type=order.order_type,
        limit_price=order.limit_price,
        status=order.status,
        broker_order_id=order.broker_order_id,
        message=order.message,
        approved_at=order.approved_at,
        submitted_at=order.submitted_at,
        filled_at=order.filled_at,
        rejected_at=order.rejected_at,
        failed_at=order.failed_at,
        canceled_at=order.canceled_at,
        last_status_at=order.last_status_at,
        submission_attempts=order.submission_attempts,
        can_approve=can_approve(order),
        can_cancel=can_cancel(order),
        is_terminal=is_terminal(order),
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


def _transaction_view(order: Order) -> TransactionView:
    order_view = _order_view(order)
    return TransactionView(
        id=order_view.id,
        symbol=order_view.symbol,
        side=order_view.side,
        quantity=order_view.quantity,
        order_type=order_view.order_type,
        limit_price=order_view.limit_price,
        status=order_view.status,
        mode=order_view.mode,
        broker_order_id=order_view.broker_order_id,
        message=order_view.message,
        approved_at=order_view.approved_at,
        submitted_at=order_view.submitted_at,
        filled_at=order_view.filled_at,
        rejected_at=order_view.rejected_at,
        failed_at=order_view.failed_at,
        canceled_at=order_view.canceled_at,
        last_status_at=order_view.last_status_at,
        submission_attempts=order_view.submission_attempts,
        can_approve=order_view.can_approve,
        can_cancel=order_view.can_cancel,
        is_terminal=order_view.is_terminal,
        created_at=order_view.created_at or order.created_at,
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


def _revoke_other_sessions(db: Session, request: Request, user_id: int) -> None:
    from datetime import UTC, datetime
    from app.core.auth import _token_hash

    session_token = request.cookies.get(settings.session_cookie_name)
    current_hash = _token_hash(session_token) if session_token else None
    sessions = db.scalars(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    ).all()
    revoked_at = datetime.now(UTC)
    for session in sessions:
        if current_hash and session.session_token_hash == current_hash:
            continue
        session.revoked_at = revoked_at
