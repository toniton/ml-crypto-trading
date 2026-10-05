import unittest
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.trading_engine_proxy import (
    AssetRuntimeSnapshot,
    EngineStatus,
    RecordedMarketDataSummary,
)
from src.recorder.market_data_store import MarketDataStore
from src.trading.local_trading_engine_proxy import LocalTradingEngineProxy


class TestLocalTradingEngineProxy(unittest.TestCase):
    def _create_proxy(
            self,
            trading_engine=None,
            managers=None,
            market_data_store=None,
            compare_backtest=None,
    ) -> LocalTradingEngineProxy:
        engine = trading_engine if trading_engine is not None else MagicMock()
        if managers is not None:
            engine.managers = managers
        return LocalTradingEngineProxy(
            trading_engine=engine,
            market_data_store=market_data_store if market_data_store is not None else MarketDataStore(),
            compare_backtest=compare_backtest if compare_backtest is not None else (lambda action: None),
        )

    def test_status_when_stopped(self):
        mock_engine = MagicMock()
        mock_engine.is_running = False
        mock_engine.monitored_assets = []
        proxy = self._create_proxy(trading_engine=mock_engine)
        status = proxy.get_status()
        self.assertIsInstance(status, EngineStatus)
        self.assertFalse(status.is_running)
        self.assertEqual(status.state, "STOPPED")
        self.assertEqual(status.monitored_assets, [])
        self.assertEqual(status.asset_count, 0)

    def test_status_when_running(self):
        mock_engine = MagicMock()
        mock_engine.is_running = True
        mock_asset = MagicMock(spec=Asset)
        mock_asset.ticker_symbol = "BTC_USD"
        mock_engine.monitored_assets = [mock_asset]

        proxy = self._create_proxy(trading_engine=mock_engine)
        status = proxy.get_status()
        self.assertTrue(status.is_running)
        self.assertEqual(status.state, "RUNNING")
        self.assertEqual(status.monitored_assets, ["BTC_USD"])
        self.assertEqual(status.asset_count, 1)

    def test_list_monitored_assets(self):
        mock_engine = MagicMock()
        mock_a1 = MagicMock(spec=Asset)
        mock_a1.ticker_symbol = "ETH_USD"
        mock_a2 = MagicMock(spec=Asset)
        mock_a2.ticker_symbol = "BTC_USD"
        mock_engine.monitored_assets = [mock_a1, mock_a2]

        proxy = self._create_proxy(trading_engine=mock_engine)
        assets = proxy.list_monitored_assets()
        self.assertEqual(assets, ["BTC_USD", "ETH_USD"])

    def test_get_asset_snapshot_not_found(self):
        mock_engine = MagicMock()
        mock_engine.monitored_assets = []
        mock_managers = MagicMock()
        mock_managers.session_manager.has_session.return_value = False
        proxy = self._create_proxy(trading_engine=mock_engine, managers=mock_managers)
        snapshot = proxy.get_asset_snapshot("UNKNOWN")
        self.assertIsNone(snapshot)

    def test_get_asset_snapshot_success(self):
        mock_engine = MagicMock()
        mock_asset = MagicMock(spec=Asset)
        mock_asset.ticker_symbol = "BTC_USD"
        mock_engine.monitored_assets = [mock_asset]
        mock_strategy = MagicMock()
        mock_strategy.name = "RSIStrategy"
        mock_strategy.ticker_symbols = {"BTC_USD"}
        mock_engine.strategies = [mock_strategy]

        mock_managers = MagicMock()
        mock_managers.session_manager.has_session.return_value = True
        mock_managers.order_manager.get_open_orders.return_value = [MagicMock(), MagicMock()]
        mock_managers.market_data_manager.get_last_price.return_value = 50000.0
        mock_context = MagicMock()
        mock_context.position_qty = 1.5
        mock_context.trades = [MagicMock()]
        mock_managers.session_manager.get_trading_context_by_symbol.return_value = mock_context

        proxy = self._create_proxy(
            trading_engine=mock_engine,
            managers=mock_managers,
        )
        snapshot = proxy.get_asset_snapshot("BTC_USD")
        self.assertIsNotNone(snapshot)
        self.assertIsInstance(snapshot, AssetRuntimeSnapshot)
        self.assertEqual(snapshot.ticker_symbol, "BTC_USD")
        self.assertEqual(snapshot.open_orders_count, 2)
        self.assertEqual(snapshot.latest_price, 50000.0)
        self.assertEqual(snapshot.position_quantity, 1.5)
        self.assertEqual(snapshot.total_trades_count, 1)
        self.assertEqual(snapshot.active_strategies, ["RSIStrategy"])

    def test_get_recorded_market_data(self):
        md_store = MarketDataStore()
        mock_obs1 = MagicMock()
        mock_obs1.timestamp = 1700000000
        mock_obs2 = MagicMock()
        mock_obs2.timestamp = 1700003600
        md_store.record("BTC_USD", mock_obs1)
        md_store.record("BTC_USD", mock_obs2)

        proxy = self._create_proxy(market_data_store=md_store)
        recorded = proxy.get_recorded_market_data()
        self.assertEqual(len(recorded), 1)
        self.assertIsInstance(recorded[0], RecordedMarketDataSummary)
        self.assertEqual(recorded[0].ticker_symbol, "BTC_USD")
        self.assertEqual(recorded[0].observation_count, 2)

    def test_update_config_delegation(self):
        mock_engine = MagicMock()
        proxy = self._create_proxy(trading_engine=mock_engine)
        config = MagicMock(spec=TradingConfig)
        proxy.update_config(config)
        mock_engine.update_config.assert_called_once_with(config)

    def test_compare_backtest_drift_delegation(self):
        mock_compare = MagicMock(return_value={"drift": 0.05})
        proxy = self._create_proxy(compare_backtest=mock_compare)
        res = proxy.compare_backtest_drift("dummy_action")
        self.assertEqual(res, {"drift": 0.05})
        mock_compare.assert_called_once_with("dummy_action")

