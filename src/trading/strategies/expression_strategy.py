from __future__ import annotations

from api.interfaces.candle import Candle
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.strategy_config import StrategyConfig
from src.core.expressions.expression_parser import ExpressionParser
from src.core.interfaces.rule_based_trading_strategy import RuleBasedTradingStrategy
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.factories.trading_expression_factory import TradingExpressionFactory


class ExpressionStrategy(RuleBasedTradingStrategy, ApplicationLoggingMixin):
    def __init__(self, config: StrategyConfig, ticker_symbols: set[str] | list[str] | None = None):
        super().__init__(ticker_symbols=ticker_symbols)
        self.config = config
        self.action = config.action
        self._parser = ExpressionParser(config.expression)

    @property
    def name(self) -> str:
        return self.config.name

    def get_quorum(
            self,
            trade_action: TradeAction,
            ticker_symbol: str,
            trading_context: TradingContext,
            market_data: MarketData,
            candles: list[Candle],
    ):
        if trade_action != self.action:
            return False

        context = TradingExpressionFactory.create_strategy_context(trading_context, market_data, candles)
        result = self._parser.parse(context)
        return bool(result)
