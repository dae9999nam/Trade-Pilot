from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import UserTradingSettings
from app.schemas import (
    SystemTradingSafetySettings,
    TradingSafetySettingsResponse,
    TradingSafetySettingsUpdate,
    UserTradingSafetySettings,
)

SYSTEM_CONTROLLED_TRADING_FIELDS = [
    "broker_mode",
    "auto_execute",
    "allow_live_trading",
    "i_understand_loss_risk",
    "creon_account_no",
    "creon_gateway_url",
    "creon_gateway_token",
]


def get_or_create_user_trading_settings(
    db: Session,
    user_id: int,
    settings: Settings,
) -> UserTradingSettings:
    row = db.scalar(select(UserTradingSettings).where(UserTradingSettings.user_id == user_id))
    if row is not None:
        return row

    row = UserTradingSettings(
        user_id=user_id,
        max_order_krw=settings.max_order_krw,
        max_position_krw=settings.max_position_krw,
        min_decision_confidence=settings.min_decision_confidence,
        require_manual_approval=True,
        live_trading_opt_in=False,
    )
    db.add(row)
    db.flush()
    return row


def update_user_trading_settings(
    row: UserTradingSettings,
    payload: TradingSafetySettingsUpdate,
    settings: Settings,
) -> None:
    if payload.max_order_krw > settings.max_order_krw:
        raise HTTPException(status_code=400, detail="Max order limit cannot exceed the system cap.")
    if payload.max_position_krw > settings.max_position_krw:
        raise HTTPException(status_code=400, detail="Max position limit cannot exceed the system cap.")
    if payload.min_decision_confidence < settings.min_decision_confidence:
        raise HTTPException(status_code=400, detail="Confidence floor cannot be lower than the system floor.")
    if payload.live_trading_opt_in and not settings.live_trading_enabled:
        raise HTTPException(status_code=400, detail="System live trading gate is disabled.")

    row.max_order_krw = payload.max_order_krw
    row.max_position_krw = payload.max_position_krw
    row.min_decision_confidence = payload.min_decision_confidence
    row.require_manual_approval = payload.require_manual_approval
    row.live_trading_opt_in = payload.live_trading_opt_in


def safety_response(
    row: UserTradingSettings,
    settings: Settings,
) -> TradingSafetySettingsResponse:
    return TradingSafetySettingsResponse(
        user=UserTradingSafetySettings(
            max_order_krw=row.max_order_krw,
            max_position_krw=row.max_position_krw,
            min_decision_confidence=row.min_decision_confidence,
            require_manual_approval=row.require_manual_approval,
            live_trading_opt_in=row.live_trading_opt_in,
        ),
        system=SystemTradingSafetySettings(
            broker_mode=settings.broker_mode,
            auto_execute=settings.auto_execute,
            system_live_trading_enabled=settings.live_trading_enabled,
            effective_live_trading_enabled=effective_live_trading_enabled(row, settings),
            max_order_krw_cap=settings.max_order_krw,
            max_position_krw_cap=settings.max_position_krw,
            min_decision_confidence_floor=settings.min_decision_confidence,
            controlled_by_system=SYSTEM_CONTROLLED_TRADING_FIELDS,
        ),
    )


def effective_live_trading_enabled(row: UserTradingSettings, settings: Settings) -> bool:
    return settings.live_trading_enabled and row.live_trading_opt_in


def effective_max_order_krw(row: UserTradingSettings, settings: Settings) -> int:
    return min(row.max_order_krw, settings.max_order_krw)


def effective_max_position_krw(
    row: UserTradingSettings,
    settings: Settings,
    request_max_position_krw: int | None = None,
) -> int:
    candidates = [row.max_position_krw, settings.max_position_krw]
    if request_max_position_krw is not None:
        candidates.append(request_max_position_krw)
    return min(candidates)


def effective_min_decision_confidence(row: UserTradingSettings, settings: Settings) -> float:
    return max(row.min_decision_confidence, settings.min_decision_confidence)


def order_notional_krw(quantity: int, price: Decimal) -> Decimal:
    return Decimal(quantity) * price
