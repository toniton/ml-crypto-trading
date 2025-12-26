import logging

from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from api.interfaces.asset import Asset
from src.trading.helpers.portfolio_helper import PortfolioHelper
from src.core.interfaces.guard import Guard


class MaxDrawDownGuard(Guard):
    @classmethod
    def _calculate_max_draw_down(cls, starting_balance: float, final_balance: float, trough_value: float) -> float:
        peak_value = max(starting_balance, final_balance)
        max_drawdown = (peak_value - trough_value) / peak_value * 100
        return max_drawdown

    def can_trade(self, trade_action: TradeAction, trading_context: TradingContext) -> bool:
        if trade_action == TradeAction.SELL:
            return True
        starting_balance = trading_context.starting_balance
        if starting_balance <= 0:
            return False
        open_positions = trading_context.open_positions
        close_positions = trading_context.close_positions

        positions = open_positions + close_positions
        positions.sort(key=lambda x: x.created_time)

        peak_value, peak_time = PortfolioHelper.calculate_peak_value(starting_balance, positions)

        filtered_positions = filter(lambda x: x.created_time > peak_time, positions)
        trough_value, _ = PortfolioHelper.calculate_trough_value(peak_value, filtered_positions)

        draw_down = (trough_value - peak_value) / peak_value
        logging.info(f"DrawDown: ${draw_down}.")

        return -self.config.max_drawdown_percentage < draw_down or draw_down == 0

    @staticmethod
    def is_enabled(asset: Asset) -> bool:
        return asset.guard_config is not None and asset.guard_config.max_drawdown_percentage is not None
