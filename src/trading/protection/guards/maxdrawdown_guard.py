from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from api.interfaces.asset import Asset
from src.trading.helpers.portfolio_helper import PortfolioHelper
from src.core.interfaces.guard import Guard
from src.core.logging.application_logging_mixin import ApplicationLoggingMixin


class MaxDrawDownGuard(ApplicationLoggingMixin, Guard):
    @classmethod
    def _calculate_max_draw_down(cls, starting_balance: float, final_balance: float, trough_value: float) -> float:
        peak_value = max(starting_balance, final_balance)
        max_drawdown = (peak_value - trough_value) / peak_value * 100
        return max_drawdown

    def can_trade(self, trade_action: TradeAction, trading_context: TradingContext, _market_data: MarketData) -> bool:
        if trade_action == TradeAction.SELL:
            return True
        starting_balance = trading_context.starting_balance
        if starting_balance <= 0:
            return False
        open_positions = trading_context.open_positions
        close_positions = trading_context.close_positions

        positions = open_positions + close_positions
        positions.sort(key=lambda x: x.timestamp)

        peak_value, peak_time = PortfolioHelper.calculate_peak_value(starting_balance, open_positions, close_positions)

        filtered_open = list(filter(lambda x: x.timestamp > peak_time if peak_time else True, open_positions))
        filtered_close = list(filter(lambda x: x.timestamp > peak_time if peak_time else True, close_positions))
        trough_value, _ = PortfolioHelper.calculate_trough_value(peak_value, filtered_open, filtered_close)

        draw_down = (trough_value - peak_value) / peak_value
        self.app_logger.debug(f"DrawDown: ${draw_down}.")

        return -self.config.max_drawdown_percentage < draw_down or draw_down == 0

    @staticmethod
    def is_enabled(asset: Asset) -> bool:
        return asset.guard_config is not None and asset.guard_config.max_drawdown_percentage is not None
