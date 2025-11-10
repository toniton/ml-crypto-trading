from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.guard import Guard


class ProtectionManager:
    guards: [int, list[Guard]] = {}

    def register_guard(self, asset_key: int, guard: Guard):
        if asset_key in self.guards:
            self.guards[asset_key].append(guard)
        else:
            self.guards[asset_key] = [guard]

    def can_trade(self, asset_key: int, trade_action: TradeAction, trading_context: TradingContext) -> bool:
        if asset_key not in self.guards:
            return True
        if not bool(len(self.guards[asset_key])):
            return True
        return all(guard.can_trade(trade_action, trading_context, ) for guard in self.guards[asset_key])
