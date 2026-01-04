from collections import defaultdict

from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.guard import Guard


class ProtectionManager:
    def __init__(self):
        self.guards: dict[int, list[Guard]] = defaultdict(list)

    def register_guard(self, asset_key: int, guard: Guard):
        self.guards[asset_key].append(guard)

    def can_trade(
            self, asset_key: int, trade_action: TradeAction,
            trading_context: TradingContext, market_data: MarketData
    ) -> bool:
        if asset_key not in self.guards:
            return True
        if not bool(len(self.guards[asset_key])):
            return True
        return all(guard.can_trade(trade_action, trading_context, market_data) for guard in self.guards[asset_key])
