from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from prediction.prediction_engine import PredictionEngine
from api.interfaces.trading_strategy import TradingStrategy
from api.interfaces.trading_context import TradingContext


class PredictionBuyStrategy(TradingStrategy):

    def __init__(self, engine: PredictionEngine):
        super().__init__()
        self.type = TradeAction.BUY
        self.engine = engine

    def get_quorum(
        self, trade_action: TradeAction,
        ticker_symbol: str, trading_context: TradingContext,
        market_data: MarketData
    ):
        return True
        # return True if self.engine.predict(ticker_symbol, market_data) == 1 else False
