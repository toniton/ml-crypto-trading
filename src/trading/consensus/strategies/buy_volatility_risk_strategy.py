from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy


class BuyVolatilityRiskStrategy(RuleBasedTradingStrategy):
    def __init__(self, risk_tolerance: float = 0.02):
        super().__init__()
        self.risk_tolerance = risk_tolerance
        self.type = TradeAction.BUY

    @staticmethod
    def calculate_volatility(candles: list[Candle]) -> float:
        if not candles:
            return 0.0

        ranges = [
            (float(c.high) - float(c.low)) / float(c.close)
            for c in candles
            if float(c.close) > 0
        ]
        return sum(ranges) / len(ranges) if ranges else 0.0

    def get_quorum(
            self,
            trade_action: TradeAction,
            _ticker_symbol: str,
            _trading_context: TradingContext,
            _market_data: MarketData,
            candles: list[Candle],
    ) -> bool:
        if trade_action != TradeAction.BUY:
            return False

        volatility = self.calculate_volatility(candles)
        return volatility <= self.risk_tolerance
