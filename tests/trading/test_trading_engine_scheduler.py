import unittest
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from src.core.interfaces.trading_scheduler import TradingScheduler
from src.trading.trading_engine import TradingEngine
from src.trading.trading_executor import TradingExecutor
from src.trading.trading_oracle import TradingOracle


class TestTradingEngineScheduler(unittest.TestCase):
    def test_start_application_registers_scheduler_correctly(self):
        # Arrange
        mock_scheduler = MagicMock(spec=TradingScheduler)
        mock_executor = MagicMock(spec=TradingExecutor)
        mock_oracle_scheduler = MagicMock(spec=TradingScheduler)
        mock_trading_oracle = MagicMock(spec=TradingOracle)

        # Mock functions to be callable
        mock_executor.create_buy_order = MagicMock()
        mock_executor.create_sell_order = MagicMock()
        mock_trading_oracle.generate_report = MagicMock()

        engine = TradingEngine(
            trading_scheduler=mock_scheduler,
            trading_executor=mock_executor,
            oracle_scheduler=mock_oracle_scheduler,
            trading_oracle=mock_trading_oracle
        )

        # Mock ThreadPoolExecutor to run tasks synchronously
        def mock_submit(fn, *args, **kwargs):
            fn(*args, **kwargs)
            return MagicMock()

        engine.thread_pool_executor.submit = mock_submit

        # Act
        engine.start_application()

        # Assert
        # We expect exactly one call to scheduler.start with our combined callback
        self.assertEqual(mock_scheduler.start.call_count, 1, "Scheduler.start should be called exactly once")
        self.assertEqual(mock_oracle_scheduler.start.call_count, 1,
                         "OracleScheduler.start should be called exactly once")

        # Verify the trading callback passed to start calls both buy and sell
        args, _ = mock_scheduler.start.call_args
        callback = args[0]
        dummy_assets = [MagicMock(spec=Asset)]

        # Execute the callback
        callback(dummy_assets)

        # Verify both executors were called
        mock_executor.create_buy_order.assert_called_once_with(dummy_assets)
        mock_executor.create_sell_order.assert_called_once_with(dummy_assets)

        # Verify the oracle callback passed to start calls report and signal
        oracle_args, _ = mock_oracle_scheduler.start.call_args
        oracle_callback = oracle_args[0]

        # Execute the oracle callback
        oracle_callback(dummy_assets)

        # Verify both oracle methods were called
        mock_trading_oracle.generate_report.assert_called_once_with(dummy_assets)
