import time

from api.interfaces.trading_context import TradingContext
from src.entities.asset import Asset
from src.trading.protection.guard import Guard


class CooldownGuard(Guard):
    def can_trade(self, trading_context: TradingContext) -> bool:
        return (trading_context.last_activity_time + self.config.cooldown_timeout) < time.time()

    @staticmethod
    def is_enabled(asset: Asset) -> bool:
        return asset.guard_config is not None and asset.guard_config.cooldown_timeout is not None

