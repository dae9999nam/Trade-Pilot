import platform
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

from config import settings
from schemas import GatewayRuntimeStatus, OrderRequest, OrderResponse, QuoteResponse


_COM_LOCK = threading.RLock()


class CreonGatewayError(RuntimeError):
    code = "creon_gateway_error"
    retryable = False

    def __init__(self, message: str, *, code: str | None = None, retryable: bool | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if retryable is not None:
            self.retryable = retryable


class CreonConfigurationError(CreonGatewayError):
    code = "creon_configuration_error"


class CreonUnavailableError(CreonGatewayError):
    code = "creon_unavailable"
    retryable = True


class CreonRequestError(CreonGatewayError):
    code = "creon_request_error"
    retryable = True


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

    def _normalize_symbol(self, symbol: str) -> str:
        normalized = symbol.strip().upper()
        if len(normalized) < 2 or len(normalized) > 16:
            raise CreonConfigurationError("Symbol length must be between 2 and 16.")
        return normalized

    def _pywin32_available(self) -> bool:
        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
        except ImportError:
            return False
        return True
