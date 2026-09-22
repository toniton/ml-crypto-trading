import unittest
from unittest.mock import Mock, call

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from src.trading.live_trading_scheduler import LiveTradingScheduler
from src.backtest.backtest_trading_scheduler import BacktestTradingScheduler


class TestLiveTradingScheduler(unittest.TestCase):
    def test_init(self):
        scheduler = LiveTradingScheduler()
        self.assertIsNotNone(scheduler)

    def test_update_schedules_registers_and_recycles_threads(self):
        scheduler = LiveTradingScheduler()
        asset_1 = Mock(spec=Asset)
        asset_1.schedule = AssetSchedule.EVERY_MINUTE
        asset_1.ticker_symbol = "BTC_USD"

        scheduler.register_assets([asset_1])
        callback = Mock()
        scheduler.start(callback)

        self.assertIn(AssetSchedule.EVERY_MINUTE, scheduler._scheduler_threads)
        self.assertEqual(len(scheduler.get_assets(AssetSchedule.EVERY_MINUTE)), 1)

        # Update schedules to EVERY_HOUR
        asset_2 = Mock(spec=Asset)
        asset_2.schedule = AssetSchedule.EVERY_HOUR
        asset_2.ticker_symbol = "ETH_USD"

        scheduler.update_schedules([asset_2])

        self.assertNotIn(AssetSchedule.EVERY_MINUTE, scheduler._scheduler_threads)
        self.assertIn(AssetSchedule.EVERY_HOUR, scheduler._scheduler_threads)
        self.assertEqual(len(scheduler.get_assets(AssetSchedule.EVERY_HOUR)), 1)
        self.assertEqual(scheduler.get_assets(AssetSchedule.EVERY_HOUR)[0].ticker_symbol, "ETH_USD")

        scheduler.stop()



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
        scheduler.on_tick(0, asset)
        callback.assert_called_once_with([asset])
        callback.reset_mock()

        # Test 2: Timestamp 1 (should NOT trigger)
        scheduler.on_tick(1, asset)
        callback.assert_not_called()

        # Test 3: Timestamp 60 (should trigger)
        scheduler.on_tick(60, asset)
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
        scheduler.on_tick(0, asset_min)
        scheduler.on_tick(0, asset_sec)
        self.assertEqual(callback.call_count, 2)

        expected_calls = [call([asset_min]), call([asset_sec])]
        callback.assert_has_calls(expected_calls, any_order=True)
        callback.reset_mock()

        # T=61:
        # Minute asset: 61 // 60 = 1, 0 // 60 = 0. 1 > 0. Triggers.
        # Second asset: 61 // 1 = 61, 0 // 1 = 0. 61 > 0. Triggers.
        scheduler.on_tick(61, asset_min)
        scheduler.on_tick(61, asset_sec)
        self.assertEqual(callback.call_count, 2)
        callback.assert_has_calls(expected_calls, any_order=True)

    def test_update_schedules(self):
        clock = Mock()
        scheduler = BacktestTradingScheduler(clock)

        asset_1 = Mock(spec=Asset)
        asset_1.schedule = AssetSchedule.EVERY_MINUTE
        asset_1.ticker_symbol = "BTC_USD"

        scheduler.register_assets([asset_1])
        callback = Mock()
        scheduler.start(callback)

        asset_2 = Mock(spec=Asset)
        asset_2.schedule = AssetSchedule.EVERY_HOUR
        asset_2.ticker_symbol = "ETH_USD"

        scheduler.update_schedules([asset_2])

        self.assertNotIn(AssetSchedule.EVERY_MINUTE, scheduler.get_registered_schedules())
        self.assertIn(AssetSchedule.EVERY_HOUR, scheduler.get_registered_schedules())
        self.assertEqual(len(scheduler.get_assets(AssetSchedule.EVERY_HOUR)), 1)
        self.assertEqual(scheduler.get_assets(AssetSchedule.EVERY_HOUR)[0].ticker_symbol, "ETH_USD")


