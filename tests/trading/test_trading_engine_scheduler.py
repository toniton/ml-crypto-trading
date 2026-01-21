import unittest
from unittest.mock import MagicMock
from src.trading.trading_engine import TradingEngine
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.trading.trading_executor import TradingExecutor
from api.interfaces.asset import Asset


class TestTradingEngineScheduler(unittest.TestCase):
    def test_start_application_registers_scheduler_correctly(self):
        # Arrange
        mock_scheduler = MagicMock(spec=TradingScheduler)
        mock_executor = MagicMock(spec=TradingExecutor)
        # Mock create_buy_order and create_sell_order to be callable
        mock_executor.create_buy_order = MagicMock()
        mock_executor.create_sell_order = MagicMock()

        engine = TradingEngine(mock_scheduler, mock_executor)

        # Act
        engine.start_application()

        # Assert
        # We expect exactly one call to scheduler.start with our combined callback
        self.assertEqual(mock_scheduler.start.call_count, 1, "Scheduler.start should be called exactly once")

        # Verify the callback passed to start calls both buy and sell
        args, _ = mock_scheduler.start.call_args
        callback = args[0]
        dummy_assets = [MagicMock(spec=Asset)]

        # Execute the callback
        callback(dummy_assets)

        # Verify both executors were called
        mock_executor.create_buy_order.assert_called_once_with(dummy_assets)
        mock_executor.create_sell_order.assert_called_once_with(dummy_assets)
