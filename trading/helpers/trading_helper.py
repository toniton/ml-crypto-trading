class TradingHelper:
    @staticmethod
    def get_instrument_name(ticker_symbol: str, currency: str = "USD", separator: str = "") -> str:
        return f"{ticker_symbol}{separator}{currency}"
