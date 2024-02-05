from trading.context.trading_context import TradingContext


class TradingContextManager:
    def __init__(self):
        self.trading_contexts = {}

    def register_trading_context(self, ticker_symbol: str, trading_context: TradingContext):
        self.trading_contexts[ticker_symbol] = trading_context

    def get_trading_context(self, ticker_symbol: str) -> TradingContext:
        return self.trading_contexts[ticker_symbol]
    