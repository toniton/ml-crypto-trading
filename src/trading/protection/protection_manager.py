from collections import defaultdict

from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.guard import Guard


class ProtectionManager:
    def __init__(self):
        self.guards: dict[int, list[Guard]] = defaultdict(list)
        self._is_paused: bool = False
        self._paused_assets: set[int] = set()

    def pause_trading(self, reason: str = "") -> None:
        self._is_paused = True

    def resume_trading(self) -> None:
        self._is_paused = False

    def pause_asset(self, asset_key: int, reason: str = "") -> None:
        self._paused_assets.add(asset_key)

    def resume_asset(self, asset_key: int) -> None:
        self._paused_assets.discard(asset_key)

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    def is_asset_paused(self, asset_key: int) -> bool:
        return self._is_paused or asset_key in self._paused_assets

    def register_guard(self, asset_key: int, guard: Guard):
        self.guards[asset_key].append(guard)

    def can_trade(
            self, asset_key: int, trade_action: TradeAction,
            trading_context: TradingContext, market_data: MarketData
    ) -> bool:
        if self._is_paused or asset_key in self._paused_assets:
            return False
        if asset_key not in self.guards:
            return True
        if not bool(len(self.guards[asset_key])):
            return True
        return all(guard.can_trade(trade_action, trading_context, market_data) for guard in self.guards[asset_key])

