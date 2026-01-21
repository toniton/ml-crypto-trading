from decimal import Decimal
from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class SellStopLossStrategy(RuleBasedTradingStrategy):

    def __init__(self, stop_loss_pct: Decimal = Decimal("0.02")):
        super().__init__()
        self.type = TradeAction.SELL
        self.stop_loss_pct = Decimal(str(stop_loss_pct))

    def get_quorum(
            self, trade_action: TradeAction,
            ticker_symbol: str, trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle]
    ):
        if trade_action != TradeAction.SELL:
            return False

        current_price = market_data.close_price
        open_positions = trading_context.open_positions

        for position in open_positions:
            price_diff = position.close_price - current_price
            loss_pct = price_diff / position.close_price
            if loss_pct >= self.stop_loss_pct:
                return True

        return False
