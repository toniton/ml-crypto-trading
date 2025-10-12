class TradingHelper:
    @staticmethod
    def get_instrument_name(
            ticker_symbol: str, currency: str = "USD", separator: str = "",
            perp: bool = False
    ) -> str:
        base = f"{ticker_symbol}{separator}{currency}"
        return f"{base}-PERP" if perp else base
