from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from api.interfaces.position_entry import PositionEntry
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.core.interfaces.guard import Guard
from src.logging.application_logging_mixin import ApplicationLoggingMixin
from src.trading.helpers.portfolio_helper import PortfolioHelper


class MaxDrawDownGuard(ApplicationLoggingMixin, Guard):
    @classmethod
    def _calculate_max_draw_down(cls, starting_balance: float, final_balance: float, trough_value: float) -> float:
        peak_value = max(starting_balance, final_balance)
        if peak_value <= 0:
            return 0.0
        max_drawdown = (peak_value - trough_value) / peak_value * 100
        return max_drawdown

    def can_trade(self, trade_action: TradeAction, trading_context: TradingContext, _market_data: MarketData) -> bool:
        if trade_action == TradeAction.SELL:
            return True

        starting_balance = Decimal(str(trading_context.starting_balance))
        if starting_balance <= Decimal("0"):
            return False

        open_positions, close_positions = self._get_window_positions(trading_context)
        if not open_positions and not close_positions:
            return True

        peak_value, peak_time = PortfolioHelper.calculate_peak_value(starting_balance, open_positions, close_positions)
        filtered_open = [p for p in open_positions if (p.timestamp > peak_time if peak_time else True)]
        filtered_close = [p for p in close_positions if (p.timestamp > peak_time if peak_time else True)]
        trough_value, _ = PortfolioHelper.calculate_trough_value(peak_value, filtered_open, filtered_close)

        if peak_value <= Decimal("0"):
            return False

        draw_down = (trough_value - peak_value) / peak_value
        self.app_logger.debug("DrawDown: %s (limit: -%s)", draw_down, self.config.max_drawdown_percentage)

        max_allowed_drawdown = -Decimal(str(self.config.max_drawdown_percentage))
        return draw_down >= max_allowed_drawdown or draw_down == Decimal("0")

    def _get_window_positions(
            self,
            trading_context: TradingContext,
    ) -> tuple[list[PositionEntry], list[PositionEntry]]:
        open_positions = list(trading_context.open_positions)
        close_positions = list(trading_context.close_positions)
        all_positions = sorted(open_positions + close_positions, key=lambda x: x.timestamp)

        period = self.config.max_drawdown_period
        if period is not None and len(all_positions) > period:
            window_set = set(all_positions[-period:])
            open_positions = [p for p in open_positions if p in window_set]
            close_positions = [p for p in close_positions if p in window_set]

        return open_positions, close_positions

    @staticmethod
    def is_enabled(asset: Asset) -> bool:
        return asset.guard_config is not None and asset.guard_config.max_drawdown_percentage is not None
