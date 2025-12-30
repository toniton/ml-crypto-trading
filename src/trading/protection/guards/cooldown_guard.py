from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from api.interfaces.asset import Asset
from src.core.interfaces.guard import Guard


class CooldownGuard(Guard):
    def can_trade(self, trade_action: TradeAction, trading_context: TradingContext, market_data: MarketData) -> bool:
        if trade_action == TradeAction.SELL:
            return True
        if trading_context.last_activity_time is None:
            return True
        return (trading_context.last_activity_time + self.config.cooldown_timeout) < market_data.timestamp

    @staticmethod
    def is_enabled(asset: Asset) -> bool:
        return asset.guard_config is not None and asset.guard_config.cooldown_timeout is not None
