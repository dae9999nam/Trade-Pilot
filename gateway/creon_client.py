import platform
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

from config import settings
from schemas import (
    AccountPositionResponse,
    AccountSnapshotResponse,
    GatewayRuntimeStatus,
    OrderRequest,
    OrderResponse,
    OrderStatusResponse,
    QuoteResponse,
)


_COM_LOCK = threading.RLock()


class CreonGatewayError(RuntimeError):
    code = "creon_gateway_error"
    retryable = False
    status_code = 503

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable
        if status_code is not None:
            self.status_code = status_code


class CreonConfigurationError(CreonGatewayError):
    code = "creon_configuration_error"


class CreonUnavailableError(CreonGatewayError):
    code = "creon_unavailable"
    retryable = True


class CreonRequestError(CreonGatewayError):
    code = "creon_request_error"
    retryable = True


class CreonOrderNotFoundError(CreonGatewayError):
    code = "creon_order_not_found"
    status_code = 404


class CreonOrderRejectedError(CreonGatewayError):
    code = "creon_order_rejected"
    status_code = 409


@dataclass(frozen=True)
class _CreonOrderRecord:
    order_number: str
    original_order_number: str | None
    symbol: str
    name: str | None
    order_quantity: int
    order_price: Decimal | None
    total_filled_quantity: int
    execution_quantity: int
    confirmed_quantity: int
    cancelable_quantity: int | None
    amend_cancel_content: str | None
    amend_cancel_code: str | None
    rejection_reason: str | None
    side_code: str | None
    exchange_code: str | None


class CreonClient:
    name = "creon"

    def runtime_status(self, *, check_creon_connection: bool = False) -> GatewayRuntimeStatus:
        python_bits = 64 if sys.maxsize > 2**32 else 32
        pywin32_available = self._pywin32_available()
        status = GatewayRuntimeStatus(
            platform=platform.system(),
            python_bits=python_bits,
            pywin32_available=pywin32_available,
            live_trading_enabled=settings.live_trading_enabled,
            account_configured=bool(settings.creon_account_no),
            token_configured=bool(settings.gateway_token),
            creon_connected=None,
        )

        if not check_creon_connection:
            return status
        if status.platform != "Windows":
            status.creon_connected = False
            status.message = "CREON Plus requires Windows."
            return status
        if status.python_bits != 32:
            status.creon_connected = False
            status.message = "CREON Plus requires a 32-bit Python process."
            return status
        if not pywin32_available:
            status.creon_connected = False
            status.message = "pywin32 is not available."
            return status

        try:
            with self._with_com_lock(), self._com_apartment() as win32com_client:
                cybos = win32com_client.Dispatch("CpUtil.CpCybos")
                status.creon_connected = bool(cybos.IsConnect)
                status.message = (
                    "CREON Plus is connected."
                    if status.creon_connected
                    else "CREON Plus is not connected."
                )
        except CreonGatewayError as exc:
            status.creon_connected = False
            status.message = str(exc)
        except Exception as exc:  # COM providers can raise pywintypes errors.
            status.creon_connected = False
            status.message = f"CREON connection check failed: {exc}"
        return status

    def readiness(self) -> GatewayRuntimeStatus:
        status = self.runtime_status(check_creon_connection=True)
        messages: list[str] = []
        if status.platform != "Windows":
            messages.append("CREON Plus requires Windows.")
        if status.python_bits != 32:
            messages.append("CREON Plus requires a 32-bit Python process.")
        if not status.pywin32_available:
            messages.append("pywin32 is not available.")
        if not status.live_trading_enabled:
            messages.append("Live trading approvals are not enabled.")
        if not status.account_configured:
            messages.append("CREON_ACCOUNT_NO is not configured.")
        if not status.token_configured:
            messages.append("GATEWAY_TOKEN is not configured.")
        if status.creon_connected is False:
            messages.append(status.message or "CREON Plus is not connected.")
        status.message = " ".join(dict.fromkeys(messages)) or status.message
        return status

    def quote(self, symbol: str) -> QuoteResponse:
        self._ensure_runtime(require_account=False)
        normalized_symbol = self._normalize_symbol(symbol)
        attempts = settings.creon_quote_retry_count + 1
        last_error: CreonGatewayError | None = None

        for attempt in range(attempts):
            try:
                return self._quote_once(normalized_symbol)
            except CreonGatewayError as exc:
                last_error = exc
                if not exc.retryable or attempt >= attempts - 1:
                    raise
                time.sleep(settings.creon_quote_retry_backoff_seconds)

        raise last_error or CreonRequestError("CREON quote request failed.")

    def order(self, request: OrderRequest) -> OrderResponse:
        self._ensure_runtime(require_account=True)
        return self._order_once(request)

    def order_status(self, broker_order_id: str) -> OrderStatusResponse:
        self._ensure_runtime(require_account=True)
        return self._order_status_once(self._normalize_broker_order_id(broker_order_id))

    def cancel_order(self, broker_order_id: str) -> OrderStatusResponse:
        self._ensure_runtime(require_account=True)
        return self._cancel_order_once(self._normalize_broker_order_id(broker_order_id))

    def account_snapshot(self) -> AccountSnapshotResponse:
        self._ensure_runtime(require_account=True)
        return self._account_snapshot_once()

    def _ensure_runtime(self, *, require_account: bool) -> None:
        if platform.system() != "Windows":
            raise CreonConfigurationError("CREON Plus requires Windows.")
        if sys.maxsize > 2**32:
            raise CreonConfigurationError("CREON Plus requires a 32-bit Python process.")
        if not settings.live_trading_enabled:
            raise CreonConfigurationError("Live trading approvals are not enabled.")
        if require_account and not settings.creon_account_no:
            raise CreonConfigurationError("CREON_ACCOUNT_NO is required.")
        if not self._pywin32_available():
            raise CreonConfigurationError("pywin32 is required in the Windows 32-bit Python environment.")

    @contextmanager
    def _with_com_lock(self) -> Iterator[None]:
        acquired = _COM_LOCK.acquire(timeout=settings.creon_com_lock_timeout_seconds)
        if not acquired:
            raise CreonUnavailableError(
                "CREON COM worker is busy. Try again after the current request finishes.",
                code="creon_com_busy",
            )
        try:
            yield
        finally:
            _COM_LOCK.release()

    @contextmanager
    def _com_apartment(self) -> Iterator[Any]:
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise CreonConfigurationError(
                "pywin32 is required in the Windows 32-bit Python environment."
            ) from exc

        pythoncom.CoInitialize()
        try:
            yield win32com.client
        finally:
            pythoncom.CoUninitialize()

    def _quote_once(self, symbol: str) -> QuoteResponse:
        with self._with_com_lock(), self._com_apartment() as win32com_client:
            try:
                stock = win32com_client.Dispatch("DsCbo1.StockMst")
                stock.SetInputValue(0, symbol)
                stock.BlockRequest()
                self._ensure_dib_success(stock, "quote")
                return QuoteResponse(
                    symbol=symbol,
                    price=self._required_decimal_header(stock, 11, "price"),
                    open_price=self._optional_decimal_header(stock, 13),
                    high_price=self._optional_decimal_header(stock, 14),
                    low_price=self._optional_decimal_header(stock, 15),
                    volume=self._optional_int_header(stock, 18),
                    source=self.name,
                    as_of=datetime.now(UTC),
                )
            except CreonGatewayError:
                raise
            except Exception as exc:
                raise CreonRequestError(f"CREON quote request failed: {exc}") from exc

    def _order_once(self, request: OrderRequest) -> OrderResponse:
        with self._with_com_lock(), self._com_apartment() as win32com_client:
            try:
                trade_util = win32com_client.Dispatch("CpTrade.CpTdUtil")
                if trade_util.TradeInit(0) != 0:
                    raise CreonUnavailableError(
                        "CpTdUtil.TradeInit failed. Check CREON login and trade password."
                    )

                cp_order = win32com_client.Dispatch("CpTrade.CpTd0311")
                cp_order.SetInputValue(0, "2" if request.side == "BUY" else "1")
                cp_order.SetInputValue(1, settings.creon_account_no)
                cp_order.SetInputValue(2, settings.creon_goods_code)
                cp_order.SetInputValue(3, request.symbol)
                cp_order.SetInputValue(4, int(request.quantity))
                cp_order.SetInputValue(5, int(request.limit_price or Decimal("0")))
                cp_order.SetInputValue(7, "0")
                cp_order.SetInputValue(8, "03" if request.order_type == "MARKET" else "01")
                cp_order.BlockRequest()

                status_code, message = self._dib_status(cp_order)
                broker_order_id = str(cp_order.GetHeaderValue(8)) if status_code == 0 else None
                return OrderResponse(
                    broker_order_id=broker_order_id,
                    status="SUBMITTED" if status_code == 0 else "REJECTED",
                    message=message,
                    creon_status_code=status_code,
                    submitted_at=datetime.now(UTC),
                )
            except CreonGatewayError:
                raise
            except Exception as exc:
                raise CreonRequestError(f"CREON order request failed: {exc}") from exc

    def _order_status_once(self, broker_order_id: str) -> OrderStatusResponse:
        with self._with_com_lock(), self._com_apartment() as win32com_client:
            try:
                self._initialize_trade(win32com_client)
                records, page_count = self._fetch_order_records_5341(win32com_client)
                return self._status_from_order_records(
                    broker_order_id,
                    records,
                    page_count=page_count,
                )
            except CreonGatewayError:
                raise
            except Exception as exc:
                raise CreonRequestError(f"CREON order status request failed: {exc}") from exc

    def _cancel_order_once(self, broker_order_id: str) -> OrderStatusResponse:
        with self._with_com_lock(), self._com_apartment() as win32com_client:
            try:
                self._initialize_trade(win32com_client)
                records, page_count = self._fetch_order_records_5341(win32com_client)
                current = self._status_from_order_records(
                    broker_order_id,
                    records,
                    page_count=page_count,
                )
                if current.status in {"FILLED", "CANCELED", "REJECTED"}:
                    return current.model_copy(
                        update={"message": f"Order is already {current.status.lower()}; no cancel was sent."}
                    )

                primary = self._primary_order_record(broker_order_id, records)
                if current.remaining_quantity is not None and current.remaining_quantity <= 0:
                    return current.model_copy(
                        update={"message": "Order has no cancelable quantity; no cancel was sent."}
                    )

                cancel = win32com_client.Dispatch("CpTrade.CpTd0314")
                cancel_order_id, status_code, cancel_message = self._submit_cancel_0314(
                    cancel,
                    broker_order_id,
                    primary.symbol,
                )

                refreshed_records, refreshed_page_count = self._fetch_order_records_5341(win32com_client)
                refreshed = self._status_from_order_records(
                    broker_order_id,
                    refreshed_records,
                    page_count=refreshed_page_count,
                )
                raw_payload = dict(refreshed.raw_payload or {})
                raw_payload["cancel_request"] = {
                    "object": "CpTrade.CpTd0314",
                    "cancel_order_id": cancel_order_id,
                    "status_code": status_code,
                }
                if refreshed.status == "CANCELED":
                    message = cancel_message or "CREON confirmed the cancellation."
                else:
                    message = (
                        f"{cancel_message or 'CREON accepted the cancel request.'} "
                        f"Current broker status is {refreshed.status}; refresh again to confirm completion."
                    )
                return refreshed.model_copy(
                    update={
                        "message": message,
                        "creon_status_code": status_code,
                        "raw_payload": raw_payload,
                    }
                )
            except CreonGatewayError:
                raise
            except Exception as exc:
                raise CreonRequestError(f"CREON order cancellation failed: {exc}") from exc

    def _initialize_trade(self, win32com_client: Any) -> None:
        trade_util = win32com_client.Dispatch("CpTrade.CpTdUtil")
        if trade_util.TradeInit(0) != 0:
            raise CreonUnavailableError(
                "CpTdUtil.TradeInit failed. Check CREON login and trade password."
            )

    def _fetch_order_records_5341(
        self,
        win32com_client: Any,
    ) -> tuple[list[_CreonOrderRecord], int]:
        history = win32com_client.Dispatch("CpTrade.CpTd5341")
        records: list[_CreonOrderRecord] = []
        page_count = 0

        while True:
            page_count += 1
            history.SetInputValue(0, settings.creon_account_no)
            history.SetInputValue(1, settings.creon_goods_code)
            history.SetInputValue(2, "")
            history.SetInputValue(3, 0)
            history.SetInputValue(4, ord("1"))
            history.SetInputValue(5, 20)
            history.SetInputValue(6, ord("2"))
            history.SetInputValue(7, ord("0"))
            history.BlockRequest()
            self._ensure_dib_success(history, "order_status")
            records.extend(self._order_records_from_5341(history))

            if not bool(getattr(history, "Continue", False)):
                break
            if page_count >= 50:
                raise CreonUnavailableError(
                    "CREON order history exceeded the maximum continuation page limit.",
                    code="creon_order_status_page_limit",
                )

        return records, page_count

    def _order_records_from_5341(self, dib: Any) -> list[_CreonOrderRecord]:
        row_count = self._required_int_header(dib, 6, "order_count")
        return [self._order_record_from_5341_row(dib, row) for row in range(row_count)]

    def _order_record_from_5341_row(self, dib: Any, row: int) -> _CreonOrderRecord:
        rejection_parts = [
            self._optional_str_data(dib, 14, row),
            self._optional_str_data(dib, 28, row),
        ]
        rejection_reason = "; ".join(dict.fromkeys(part for part in rejection_parts if part)) or None
        return _CreonOrderRecord(
            order_number=self._required_order_number_data(dib, 1, row, "order_number"),
            original_order_number=self._optional_order_number_data(dib, 2, row),
            symbol=self._normalize_account_symbol(
                self._required_str_data(dib, 3, row, "symbol")
            ),
            name=self._optional_str_data(dib, 4, row),
            order_quantity=self._required_int_data(dib, 7, row, "order_quantity"),
            order_price=self._optional_decimal_data(dib, 8, row),
            total_filled_quantity=self._optional_int_data(dib, 9, row) or 0,
            execution_quantity=self._optional_int_data(dib, 10, row) or 0,
            confirmed_quantity=self._optional_int_data(dib, 12, row) or 0,
            cancelable_quantity=self._optional_int_data(dib, 22, row),
            amend_cancel_content=self._optional_str_data(dib, 13, row),
            amend_cancel_code=self._optional_str_data(dib, 36, row),
            rejection_reason=rejection_reason,
            side_code=self._optional_str_data(dib, 35, row),
            exchange_code=self._optional_str_data(dib, 41, row),
        )

    def _status_from_order_records(
        self,
        broker_order_id: str,
        records: list[_CreonOrderRecord],
        *,
        page_count: int = 1,
    ) -> OrderStatusResponse:
        primary_records = [record for record in records if record.order_number == broker_order_id]
        if not primary_records:
            raise CreonOrderNotFoundError(
                "CREON did not return the order in today's CpTd5341 order history."
            )

        related_records = [
            record
            for record in records
            if record.order_number == broker_order_id
            or record.original_order_number == broker_order_id
        ]
        order_quantity = max(record.order_quantity for record in primary_records)
        if order_quantity <= 0:
            raise CreonRequestError("CREON order history returned a non-positive order quantity.")

        filled_quantity = max(record.total_filled_quantity for record in primary_records)
        cancelable_values = [
            record.cancelable_quantity
            for record in primary_records
            if record.cancelable_quantity is not None
        ]
        cancelable_quantity = max(cancelable_values) if cancelable_values else None
        primary_rejection = next(
            (record.rejection_reason for record in primary_records if record.rejection_reason),
            None,
        )
        successful_cancel_records = [
            record
            for record in related_records
            if record.original_order_number == broker_order_id
            and self._is_cancel_record(record)
            and not record.rejection_reason
        ]
        cancellation_confirmed = any(
            record.confirmed_quantity > 0 for record in successful_cancel_records
        ) or bool(successful_cancel_records and cancelable_quantity == 0)

        if filled_quantity >= order_quantity:
            status = "FILLED"
            remaining_quantity = 0
            message = "CREON reports the order as fully filled."
        elif primary_rejection and filled_quantity == 0:
            status = "REJECTED"
            remaining_quantity = 0
            message = f"CREON rejected the order: {primary_rejection}"
        elif cancellation_confirmed:
            status = "CANCELED"
            remaining_quantity = 0
            message = "CREON reports the remaining order quantity as canceled."
        else:
            remaining_quantity = (
                cancelable_quantity
                if cancelable_quantity is not None
                else max(order_quantity - filled_quantity, 0)
            )
            if filled_quantity > 0:
                status = "PARTIALLY_FILLED"
                message = "CREON reports a partial fill with remaining quantity still open."
            else:
                status = "SUBMITTED"
                message = "CREON reports the order as accepted with no observed fill."

        return OrderStatusResponse(
            broker_order_id=broker_order_id,
            status=status,
            message=message,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            as_of=datetime.now(UTC),
            raw_payload={
                "object": "CpTrade.CpTd5341",
                "page_count": page_count,
                "matched_record_count": len(related_records),
                "order_quantity": order_quantity,
                "cancelable_quantity": cancelable_quantity,
                "records": [self._order_record_payload(record) for record in related_records],
            },
        )

    def _primary_order_record(
        self,
        broker_order_id: str,
        records: list[_CreonOrderRecord],
    ) -> _CreonOrderRecord:
        try:
            return next(record for record in records if record.order_number == broker_order_id)
        except StopIteration as exc:
            raise CreonOrderNotFoundError(
                "CREON did not return the original order required for cancellation."
            ) from exc

    def _submit_cancel_0314(
        self,
        dib: Any,
        broker_order_id: str,
        symbol: str,
    ) -> tuple[str | None, int, str]:
        dib.SetInputValue(1, int(broker_order_id))
        dib.SetInputValue(2, settings.creon_account_no)
        dib.SetInputValue(3, settings.creon_goods_code)
        dib.SetInputValue(4, symbol)
        dib.SetInputValue(5, 0)
        dib.BlockRequest()
        status_code, message = self._dib_status(dib)
        if status_code != 0:
            raise CreonOrderRejectedError(
                f"CREON cancel request was rejected with status {status_code}: {message}",
                code="creon_order_cancel_rejected",
            )
        cancel_order_id = self._optional_order_number_header(dib, 6)
        return cancel_order_id, status_code, message

    def _is_cancel_record(self, record: _CreonOrderRecord) -> bool:
        return record.amend_cancel_code == "3" or (
            record.amend_cancel_content is not None
            and "cancel" in record.amend_cancel_content.casefold()
        ) or (
            record.amend_cancel_content is not None
            and "취소" in record.amend_cancel_content
        )

    def _order_record_payload(self, record: _CreonOrderRecord) -> dict[str, Any]:
        return {
            "order_number": record.order_number,
            "original_order_number": record.original_order_number,
            "symbol": record.symbol,
            "order_quantity": record.order_quantity,
            "total_filled_quantity": record.total_filled_quantity,
            "execution_quantity": record.execution_quantity,
            "confirmed_quantity": record.confirmed_quantity,
            "cancelable_quantity": record.cancelable_quantity,
            "amend_cancel_code": record.amend_cancel_code,
            "rejection_reason": record.rejection_reason,
            "side_code": record.side_code,
            "exchange_code": record.exchange_code,
        }

    def _account_snapshot_once(self) -> AccountSnapshotResponse:
        with self._with_com_lock(), self._com_apartment() as win32com_client:
            try:
                trade_util = win32com_client.Dispatch("CpTrade.CpTdUtil")
                if trade_util.TradeInit(0) != 0:
                    raise CreonUnavailableError(
                        "CpTdUtil.TradeInit failed. Check CREON login and trade password."
                    )

                account = settings.creon_account_no
                if not account:
                    raise CreonConfigurationError("CREON_ACCOUNT_NO is required.")

                balance = win32com_client.Dispatch("CpTrade.CpTd6033")
                positions: list[AccountPositionResponse] = []
                page_count = 0

                while True:
                    page_count += 1
                    balance.SetInputValue(0, account)
                    balance.SetInputValue(1, settings.creon_goods_code)
                    balance.SetInputValue(2, 50)
                    balance.BlockRequest()
                    self._ensure_dib_success(balance, "account_snapshot")
                    positions.extend(self._positions_from_6033(balance))

                    if not bool(getattr(balance, "Continue", False)):
                        break
                    if page_count >= 20:
                        raise CreonUnavailableError(
                            "CREON account snapshot exceeded the maximum continuation page limit.",
                            code="creon_account_snapshot_page_limit",
                        )

                return AccountSnapshotResponse(
                    source=self.name,
                    cash_krw=None,
                    positions=positions,
                    as_of=datetime.now(UTC),
                    raw_payload={
                        "object": "CpTrade.CpTd6033",
                        "goods_code": settings.creon_goods_code,
                        "page_count": page_count,
                        "position_count": len(positions),
                    },
                )
            except CreonGatewayError:
                raise
            except Exception as exc:
                raise CreonRequestError(f"CREON account snapshot request failed: {exc}") from exc

    def _positions_from_6033(self, dib: Any) -> list[AccountPositionResponse]:
        row_count = self._required_int_header(dib, 7, "position_count")
        positions: list[AccountPositionResponse] = []
        for row in range(row_count):
            position = self._position_from_6033_row(dib, row)
            if position.quantity != 0:
                positions.append(position)
        return positions

    def _position_from_6033_row(self, dib: Any, row: int) -> AccountPositionResponse:
        raw_symbol = self._required_str_data(dib, 12, row, "symbol")
        raw_market_price = self._optional_decimal_data(dib, 9, row)
        return AccountPositionResponse(
            symbol=self._normalize_account_symbol(raw_symbol),
            quantity=self._required_int_data(dib, 7, row, "quantity"),
            name=self._optional_str_data(dib, 0, row),
            avg_price=self._optional_decimal_data(dib, 17, row),
            market_price=abs(raw_market_price) if raw_market_price is not None else None,
            available_quantity=self._optional_int_data(dib, 15, row),
            market_value=self._optional_decimal_data(dib, 11, row),
            raw_payload={
                "source": "CpTrade.CpTd6033",
                "row": row,
                "fields": {
                    "name": 0,
                    "quantity": 7,
                    "market_price": 9,
                    "market_value": 11,
                    "symbol": 12,
                    "available_quantity": 15,
                    "avg_price": 17,
                },
            },
        )

    def _ensure_dib_success(self, dib: Any, context: str) -> None:
        status_code, message = self._dib_status(dib)
        if status_code != 0:
            raise CreonRequestError(
                f"CREON {context} request failed with status {status_code}: {message}",
                code=f"creon_{context}_rejected",
            )

    def _dib_status(self, dib: Any) -> tuple[int, str]:
        try:
            status_code = int(dib.GetDibStatus())
        except Exception as exc:
            raise CreonRequestError(f"Failed to read CREON DIB status: {exc}") from exc
        try:
            message = str(dib.GetDibMsg1())
        except Exception:
            message = ""
        return status_code, message

    def _required_decimal_header(self, dib: Any, header: int, field_name: str) -> Decimal:
        value = self._optional_decimal_header(dib, header)
        if value is None:
            raise CreonRequestError(f"CREON quote did not include {field_name}.")
        return value

    def _required_int_header(self, dib: Any, header: int, field_name: str) -> int:
        value = self._optional_int_header(dib, header)
        if value is None:
            raise CreonRequestError(f"CREON response did not include {field_name}.")
        return value

    def _optional_decimal_header(self, dib: Any, header: int) -> Decimal | None:
        value = dib.GetHeaderValue(header)
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise CreonRequestError(f"Invalid CREON decimal header {header}: {value}") from exc

    def _optional_int_header(self, dib: Any, header: int) -> int | None:
        value = dib.GetHeaderValue(header)
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise CreonRequestError(f"Invalid CREON integer header {header}: {value}") from exc

    def _optional_order_number_header(self, dib: Any, header: int) -> str | None:
        return self._normalize_optional_order_number(dib.GetHeaderValue(header))

    def _required_str_data(self, dib: Any, field: int, row: int, field_name: str) -> str:
        value = self._optional_str_data(dib, field, row)
        if not value:
            raise CreonRequestError(f"CREON account row {row} did not include {field_name}.")
        return value

    def _optional_str_data(self, dib: Any, field: int, row: int) -> str | None:
        value = dib.GetDataValue(field, row)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def _required_int_data(self, dib: Any, field: int, row: int, field_name: str) -> int:
        value = self._optional_int_data(dib, field, row)
        if value is None:
            raise CreonRequestError(f"CREON account row {row} did not include {field_name}.")
        return value

    def _optional_int_data(self, dib: Any, field: int, row: int) -> int | None:
        value = dib.GetDataValue(field, row)
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise CreonRequestError(f"Invalid CREON integer data field {field} row {row}: {value}") from exc

    def _required_order_number_data(
        self,
        dib: Any,
        field: int,
        row: int,
        field_name: str,
    ) -> str:
        value = self._optional_order_number_data(dib, field, row)
        if value is None:
            raise CreonRequestError(f"CREON order row {row} did not include {field_name}.")
        return value

    def _optional_order_number_data(self, dib: Any, field: int, row: int) -> str | None:
        return self._normalize_optional_order_number(dib.GetDataValue(field, row))

    def _optional_decimal_data(self, dib: Any, field: int, row: int) -> Decimal | None:
        value = dib.GetDataValue(field, row)
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise CreonRequestError(f"Invalid CREON decimal data field {field} row {row}: {value}") from exc

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if len(normalized) < 2 or len(normalized) > 16:
            raise CreonConfigurationError("Symbol length must be between 2 and 16.")
        return normalized

    def _normalize_broker_order_id(self, broker_order_id: str) -> str:
        normalized = broker_order_id.strip()
        if not normalized.isdigit() or int(normalized) <= 0:
            raise CreonConfigurationError(
                "CREON broker_order_id must be a positive numeric order number.",
                code="creon_invalid_order_id",
                status_code=400,
            )
        return str(int(normalized))

    def _normalize_optional_order_number(self, value: object) -> str | None:
        if value is None or value == "":
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise CreonRequestError(f"Invalid CREON order number: {value}") from exc
        return str(normalized) if normalized > 0 else None

    def _normalize_account_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if normalized.isdigit() and len(normalized) == 6:
            return f"A{normalized}"
        return normalized

    def _pywin32_available(self) -> bool:
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except ImportError:
            return False
        return True
