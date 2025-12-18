from __future__ import annotations

from src.trading.trading_executor import TradingExecutor
from src.trading.trading_scheduler import TradingScheduler


class TradingEngine:
    def __init__(
            self,
            trading_scheduler: TradingScheduler,
            trading_executor: TradingExecutor
    ):
        self.trading_scheduler = trading_scheduler
        self.trading_executor = trading_executor

    def init_application(self):
        self.trading_executor.init_application()
        self.trading_scheduler.start(self.trading_executor.create_buy_order)
        self.trading_scheduler.start(self.trading_executor.check_unclosed_orders)

    def print_context(self) -> None:
        self.trading_executor.print_context()
