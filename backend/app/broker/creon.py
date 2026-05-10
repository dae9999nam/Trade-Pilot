import platform
import sys
from decimal import Decimal

from app.broker.base import Broker, BrokerOrder, BrokerOrderResult
from app.core.config import Settings
from app.schemas import MarketSnapshot


class CreonBroker(Broker):
    name = "creon"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ensure_runtime()

    def _ensure_runtime(self) -> None:
        if platform.system() != "Windows":
            raise RuntimeError("CREON Plus requires Windows because it is a COM API.")
        if sys.maxsize > 2**32:
            raise RuntimeError("CREON Plus callers must run in a 32-bit Python process.")
        if not self.settings.live_trading_enabled:
            raise RuntimeError("Live trading requires explicit environment approvals.")

    def _dispatch(self, name: str):
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError("Install pywin32 in the 32-bit Windows Python environment.") from exc

        pythoncom.CoInitialize()
        return win32com.client.Dispatch(name)

    def get_quote(self, symbol: str) -> MarketSnapshot:
        stock = self._dispatch("DsCbo1.StockMst")
        stock.SetInputValue(0, symbol)
        stock.BlockRequest()

        price = Decimal(str(stock.GetHeaderValue(11)))
        open_price = Decimal(str(stock.GetHeaderValue(13)))
        high_price = Decimal(str(stock.GetHeaderValue(14)))
        low_price = Decimal(str(stock.GetHeaderValue(15)))
        volume = int(stock.GetHeaderValue(18))

        return MarketSnapshot(
            symbol=symbol,
            price=price,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            volume=volume,
            source=self.name,
        )

    def place_order(self, order: BrokerOrder) -> BrokerOrderResult:
        if not self.settings.creon_account_no:
            raise RuntimeError("CREON_ACCOUNT_NO is required for live orders.")

        trade_util = self._dispatch("CpTrade.CpTdUtil")
        if trade_util.TradeInit(0) != 0:
            raise RuntimeError("CpTdUtil.TradeInit failed. Check CREON login and trade password.")

        cp_order = self._dispatch("CpTrade.CpTd0311")
        cp_order.SetInputValue(0, "2" if order.side == "BUY" else "1")
        cp_order.SetInputValue(1, self.settings.creon_account_no)
        cp_order.SetInputValue(2, self.settings.creon_goods_code)
        cp_order.SetInputValue(3, order.symbol)
        cp_order.SetInputValue(4, int(order.quantity))
        cp_order.SetInputValue(5, int(order.limit_price or Decimal("0")))
        cp_order.SetInputValue(7, "0")
        cp_order.SetInputValue(8, "03" if order.order_type == "MARKET" else "01")

        cp_order.BlockRequest()
        status_code = cp_order.GetDibStatus()
        message = cp_order.GetDibMsg1()
        broker_order_id = str(cp_order.GetHeaderValue(8)) if status_code == 0 else None
        return BrokerOrderResult(
            broker_order_id=broker_order_id,
            status="SUBMITTED" if status_code == 0 else "REJECTED",
            message=message,
        )

