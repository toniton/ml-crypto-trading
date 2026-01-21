import unittest
from unittest.mock import MagicMock
from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from backtest.backtest_clock import BacktestClock
from backtest.backtest_trading_scheduler import BacktestTradingScheduler


class TestSchedulerIsolation(unittest.TestCase):
    def test_schedule_isolation(self):
        # Setup mocking
        clock = MagicMock(spec=BacktestClock)
        scheduler = BacktestTradingScheduler(clock)

        # Register a frequent schedule (EVERY_MINUTE) and a sparse one (EVERY_DAY)
        scheduler.register_assets([MagicMock(spec=Asset, schedule=AssetSchedule.EVERY_MINUTE)])
        scheduler.register_assets([MagicMock(spec=Asset, schedule=AssetSchedule.EVERY_DAY)])

        callback = MagicMock()
        scheduler.start(callback)

        # Asset 1 (DOGE) has EVERY_DAY (86400s)
        doge = MagicMock(spec=Asset, ticker_symbol="DOGE", schedule=AssetSchedule.EVERY_DAY)

        # Time T=0
        scheduler.on_tick(0, doge)
        self.assertEqual(callback.call_count, 1)

        # Time T=60 (1 minute later).
        # Previously, DOGE would have triggered here because the scheduler checked ALL registered schedules
        # (including EVERY_MINUTE).
        scheduler.on_tick(60, doge)
        self.assertEqual(callback.call_count, 1, "DOGE should NOT have triggered after only 1 minute")

        # Time T=86400 (1 day later)
        scheduler.on_tick(86400, doge)
        self.assertEqual(callback.call_count, 2, "DOGE SHOULD trigger after 1 day")
