from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.trade_action import TradeAction

from src.backtest.execution.slippage.slippage_model import SlippageModel


class FixedTickSlippage(SlippageModel):
    def __init__(self, ticks: int = 2):
        self._ticks = Decimal(str(ticks))

    def apply(self, trade_action: TradeAction, price: Decimal, asset: Asset) -> Decimal:
        tick_size = Decimal(10) ** Decimal(-asset.quote_decimals)
        slippage = self._ticks * tick_size
        if trade_action == TradeAction.BUY:
            return price + slippage
        return price - slippage
