import unittest
from unittest.mock import Mock, call

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.trading.live_trading_scheduler import LiveTradingScheduler
from backtest.backtest_trading_scheduler import BacktestTradingScheduler


class TestLiveTradingScheduler(unittest.TestCase):
    def test_init(self):
        scheduler = LiveTradingScheduler()
        self.assertIsNotNone(scheduler)


class TestBacktestTradingScheduler(unittest.TestCase):
    def test_on_tick_triggers_callback(self):
        # Setup
        # Mock clock (not used but required)
        clock = Mock()
        scheduler = BacktestTradingScheduler(clock)

        # Register asset
        asset = Mock(spec=Asset)
        asset.name = "TestAsset"
        asset.schedule = AssetSchedule.EVERY_MINUTE
        scheduler.register_assets([asset])

        callback = Mock()
        scheduler.start(callback)

        # Test 1: Timestamp 0 (should trigger?)
        # 0 % 60 == 0. Yes.
        scheduler.on_tick(0)
        callback.assert_called_once_with([asset])
        callback.reset_mock()

        # Test 2: Timestamp 1 (should NOT trigger)
        scheduler.on_tick(1)
        callback.assert_not_called()

        # Test 3: Timestamp 60 (should trigger)
        scheduler.on_tick(60)
        callback.assert_called_once_with([asset])

    def test_multiple_assets_different_schedules(self):
        clock = Mock()
        scheduler = BacktestTradingScheduler(clock)

        asset_min = Mock(spec=Asset)
        asset_min.schedule = AssetSchedule.EVERY_MINUTE
        asset_min.name = "MinAsset"

        asset_sec = Mock(spec=Asset)
        asset_sec.schedule = AssetSchedule.EVERY_SECOND
        asset_sec.name = "SecAsset"

        scheduler.register_assets([asset_min, asset_sec])

        callback = Mock()
        scheduler.start(callback)

        # T=0: Both match (0 % 60 == 0, 0 % 1 == 0)
        scheduler.on_tick(0)
        self.assertEqual(callback.call_count, 2)

        expected_calls = [call([asset_min]), call([asset_sec])]
        callback.assert_has_calls(expected_calls, any_order=True)
        callback.reset_mock()

        # T=1: Sec matches (1%1==0), Min no (1%60!=0)
        scheduler.on_tick(1)
        callback.assert_called_once_with([asset_sec])
