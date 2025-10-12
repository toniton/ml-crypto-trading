from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.trading.protection.guard import Guard


class ProtectionManager:
    guards: [str, list[Guard]] = {}

    def register_guard(self, ticker_symbol: str, guard: Guard):
        if ticker_symbol in self.guards:
            self.guards[ticker_symbol].append(guard)
        else:
            self.guards[ticker_symbol] = [guard]

    def can_trade(self, ticker_symbol: str, trade_action: TradeAction, trading_context: TradingContext) -> bool:
        if ticker_symbol not in self.guards:
            return True
        if not bool(len(self.guards[ticker_symbol])):
            return True
        return all(guard.can_trade(trade_action, trading_context) for guard in self.guards[ticker_symbol])
