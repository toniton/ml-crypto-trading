class TradingHelper:
    @staticmethod
    def format_ticker_symbol(
            ticker_symbol: str, separator: str = "", suffix: str = None
    ) -> str:
        base = f"{ticker_symbol.replace('_', separator)}"
        return f"{base}{suffix}" if suffix else base
