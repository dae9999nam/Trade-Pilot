import platform
import sys
from decimal import Decimal

from config import settings
from schemas import OrderRequest, OrderResponse, QuoteResponse


class CreonClient:
    def __init__(self) -> None:
        self._ensure_runtime()

    def _ensure_runtime(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("CREON Plus requires Windows.")
        if sys.maxsize > 2**32:
            raise RuntimeError("CREON Plus requires a 32-bit Python process.")
        if not settings.live_trading_enabled:
            raise RuntimeError("Live trading approvals are not enabled.")

    def _dispatch(self, name: str):
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError("pywin32 is required in the Windows 32-bit Python env.") from exc

        pythoncom.CoInitialize()
        return win32com.client.Dispatch(name)

    def quote(self, symbol: str) -> QuoteResponse:
        stock = self._dispatch("DsCbo1.StockMst")
        stock.SetInputValue(0, symbol)
        stock.BlockRequest()
        return QuoteResponse(
            symbol=symbol,
            price=Decimal(str(stock.GetHeaderValue(11))),
            open_price=Decimal(str(stock.GetHeaderValue(13))),
            high_price=Decimal(str(stock.GetHeaderValue(14))),
            low_price=Decimal(str(stock.GetHeaderValue(15))),
            volume=int(stock.GetHeaderValue(18)),
        )

    def order(self, request: OrderRequest) -> OrderResponse:
        if not settings.creon_account_no:
            raise RuntimeError("CREON_ACCOUNT_NO is required.")

        trade_util = self._dispatch("CpTrade.CpTdUtil")
        if trade_util.TradeInit(0) != 0:
            raise RuntimeError("CpTdUtil.TradeInit failed. Check CREON login and trade password.")

        cp_order = self._dispatch("CpTrade.CpTd0311")
        cp_order.SetInputValue(0, "2" if request.side == "BUY" else "1")
        cp_order.SetInputValue(1, settings.creon_account_no)
        cp_order.SetInputValue(2, settings.creon_goods_code)
        cp_order.SetInputValue(3, request.symbol)
        cp_order.SetInputValue(4, int(request.quantity))
        cp_order.SetInputValue(5, int(request.limit_price or Decimal("0")))
        cp_order.SetInputValue(7, "0")
        cp_order.SetInputValue(8, "03" if request.order_type == "MARKET" else "01")
        cp_order.BlockRequest()

        status_code = cp_order.GetDibStatus()
        message = cp_order.GetDibMsg1()
        broker_order_id = str(cp_order.GetHeaderValue(8)) if status_code == 0 else None
        return OrderResponse(
            broker_order_id=broker_order_id,
            status="SUBMITTED" if status_code == 0 else "REJECTED",
            message=message,
        )
