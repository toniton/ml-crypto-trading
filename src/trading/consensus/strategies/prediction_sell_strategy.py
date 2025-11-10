from api.interfaces.candle import Candle
from src.core.interfaces.machine_learning_trading_strategy import MachineLearningTradingStrategy
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
# from prediction.prediction_engine import PredictionEngine
from api.interfaces.trading_context import TradingContext


class PredictionSellTradingStrategy(MachineLearningTradingStrategy):

    # def __init__(self, engine: PredictionEngine):
    #     super().__init__()
    #     self.type = TradeAction.SELL
    #     self.engine = engine

    def get_quorum(
        self, trade_action: TradeAction,
        ticker_symbol: str, trading_context: TradingContext,
        market_data: MarketData,
        candles: list[Candle]
    ):
        # return True if self.engine.predict(ticker_symbol, market_data) == 0 else False
        return True
