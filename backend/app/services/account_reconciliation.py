from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.broker.base import Broker, BrokerAccountPosition, BrokerAccountSnapshot
from app.core.config import Settings
from app.models import Position
from app.schemas import (
    AccountPositionSnapshot,
    AccountReconciliationStatus,
    AccountReconciliationResponse,
    AccountReconciliationRow,
    BrokerSnapshotStatus,
)


class AccountReconciliationService:
    def __init__(self, db: Session, broker: Broker, settings: Settings, user_id: int) -> None:
        self.db = db
        self.broker = broker
        self.settings = settings
        self.user_id = user_id

    def run(self) -> AccountReconciliationResponse:
        app_positions = self._app_positions()
        if self.settings.broker_mode == "paper":
            snapshot = BrokerAccountSnapshot(
                source="paper",
                positions=[
                    BrokerAccountPosition(
                        symbol=position.symbol,
                        quantity=position.quantity,
                        avg_price=position.avg_price,
                        market_price=position.market_price,
                    )
                    for position in app_positions
                ],
                as_of=datetime.now(UTC),
            )
            return self._build_response(
                app_positions=app_positions,
                snapshot=snapshot,
                broker_status="PAPER",
                message="Paper mode uses the application database as the broker ledger.",
            )

        try:
            snapshot = self.broker.get_account_snapshot()
        except Exception as exc:
            return self._unavailable_response(app_positions, str(exc))

        return self._build_response(
            app_positions=app_positions,
            snapshot=snapshot,
            broker_status="SYNCED",
            message="Broker account snapshot loaded and compared with application positions.",
        )

    def _app_positions(self) -> list[Position]:
        return list(
            self.db.scalars(
                select(Position)
                .where(Position.user_id == self.user_id, Position.quantity != 0)
                .order_by(Position.symbol.asc())
            ).all()
        )

    def _unavailable_response(self, app_positions: list[Position], reason: str) -> AccountReconciliationResponse:
        rows = [
            AccountReconciliationRow(
                symbol=position.symbol,
                app_quantity=position.quantity,
                broker_quantity=None,
                app_market_value=self._market_value(position.quantity, position.market_price),
                broker_market_value=None,
                status="BROKER_UNAVAILABLE",
                message="Broker account snapshot is unavailable.",
            )
            for position in app_positions
        ]
        return AccountReconciliationResponse(
            broker_mode=self.settings.broker_mode,
            broker_source=self.broker.name,
            broker_status="UNAVAILABLE",
            message=reason,
            app_positions=[self._app_snapshot(position) for position in app_positions],
            broker_positions=[],
            rows=rows,
            as_of=datetime.now(UTC),
        )

    def _build_response(
        self,
        *,
        app_positions: list[Position],
        snapshot: BrokerAccountSnapshot,
        broker_status: BrokerSnapshotStatus,
        message: str,
    ) -> AccountReconciliationResponse:
        app_by_symbol = {position.symbol: position for position in app_positions if position.quantity != 0}
        broker_by_symbol = {
            position.symbol: position for position in snapshot.positions if position.quantity != 0
        }
        symbols = sorted({*app_by_symbol.keys(), *broker_by_symbol.keys()})
        rows = [
            self._row_for(symbol, app_by_symbol.get(symbol), broker_by_symbol.get(symbol))
            for symbol in symbols
        ]
        return AccountReconciliationResponse(
            broker_mode=self.settings.broker_mode,
            broker_source=snapshot.source,
            broker_status=broker_status,
            message=message,
            cash_krw=snapshot.cash_krw,
            app_positions=[self._app_snapshot(position) for position in app_positions],
            broker_positions=[
                self._broker_snapshot(position)
                for position in sorted(snapshot.positions, key=lambda item: item.symbol)
                if position.quantity != 0
            ],
            rows=rows,
            as_of=snapshot.as_of,
        )

    def _row_for(
        self,
        symbol: str,
        app_position: Position | None,
        broker_position: BrokerAccountPosition | None,
    ) -> AccountReconciliationRow:
        app_quantity = app_position.quantity if app_position else 0
        broker_quantity = broker_position.quantity if broker_position else None
        app_market_value = (
            self._market_value(app_position.quantity, app_position.market_price)
            if app_position
            else Decimal("0")
        )
        broker_market_value = (
            self._market_value(broker_position.quantity, broker_position.market_price)
            if broker_position and broker_position.market_price is not None
            else None
        )

        if app_position and broker_position:
            status: AccountReconciliationStatus = (
                "MATCHED" if app_position.quantity == broker_position.quantity else "QUANTITY_MISMATCH"
            )
            message = None if status == "MATCHED" else "Application and broker quantities differ."
        elif app_position:
            status = "MISSING_IN_BROKER"
            message = "Position exists in the application database but not in the broker snapshot."
        else:
            status = "MISSING_IN_APP"
            message = "Position exists in the broker snapshot but not in the application database."

        return AccountReconciliationRow(
            symbol=symbol,
            app_quantity=app_quantity,
            broker_quantity=broker_quantity,
            app_market_value=app_market_value,
            broker_market_value=broker_market_value,
            status=status,
            message=message,
        )

    def _app_snapshot(self, position: Position) -> AccountPositionSnapshot:
        return AccountPositionSnapshot(
            symbol=position.symbol,
            quantity=position.quantity,
            avg_price=position.avg_price,
            market_price=position.market_price,
        )

    def _broker_snapshot(self, position: BrokerAccountPosition) -> AccountPositionSnapshot:
        return AccountPositionSnapshot(
            symbol=position.symbol,
            quantity=position.quantity,
            avg_price=position.avg_price,
            market_price=position.market_price,
        )

    def _market_value(self, quantity: int, price: Decimal) -> Decimal:
        return Decimal(quantity) * price
