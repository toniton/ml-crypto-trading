from api.interfaces.trading_context import TradingContext
from src.trading.protection.guard import Guard


class ProtectionManager:
    guards: [str, list[Guard]] = {}

    def register_guard(self, ticker_symbol: str, guard: Guard):
        if ticker_symbol in self.guards:
            self.guards[ticker_symbol].append(guard)
        else:
            self.guards[ticker_symbol] = [guard]

    def can_trade(self, ticker_symbol: str, trading_context: TradingContext) -> bool:
        if ticker_symbol not in self.guards:
            return True
        if bool(len(self.guards[ticker_symbol])) is False:
            return True
        return all(guard.can_trade(trading_context) for guard in self.guards[ticker_symbol])
