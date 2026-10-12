from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from api.interfaces.backtest_run_spec import (
    BacktestConfigurationSourceType,
    BacktestConfigurationSpec,
    BacktestRunSpec,
)
from src.server.services.backtest_application_service import BacktestApplicationService


class TestBacktestApplicationServiceLoopIndependence:  # pylint: disable=attribute-defined-outside-init
    def setup_method(self):
        self.mock_db = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_db.get_unit_of_work.return_value.__enter__.return_value = self.mock_uow
        self.mock_repo = MagicMock()
        self.mock_uow.get_repository.return_value = self.mock_repo

        self.mock_vcs = MagicMock()
        self.mock_dataset = MagicMock()
        self.mock_store = MagicMock()

        self.service = BacktestApplicationService(
            db_manager=self.mock_db,
            vcs_service=self.mock_vcs,
            dataset_service=self.mock_dataset,
            market_data_store=self.mock_store,
        )

    @patch.object(BacktestApplicationService, "_execute_run")
    def test_start_backtest_run_succeeds_in_worker_thread_without_event_loop(
            self,
            mock_exec_run,
    ):
        self.mock_vcs.checkout.return_value = {
            "dynamic_quantity": "0.01",
            "assets": [
                {
                    "name": "Bitcoin",
                    "base_ticker_symbol": "BTC",
                    "quote_ticker_symbol": "USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "min_quantity": 0.001,
                    "quote_decimals": 2,
                    "quantity_decimals": 4,
                    "candles_timeframe": "MIN1",
                    "schedule": 1,
                    "strategies": [],
                    "consensus": {"buy": 1.0, "sell": 0.5},
                }
            ],
        }

        spec = BacktestRunSpec(
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash="commit_hash_123",
            ),
        )

        def run_in_pool():
            return self.service.start_backtest_run(spec)

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run_in_pool)
            session = future.result(timeout=2.0)

        assert session is not None
        assert session.ticker_symbol == "BTC_USD"
        self.mock_repo.save_session.assert_called_once()
        mock_exec_run.assert_called_once()

    @patch.object(BacktestApplicationService, "_execute_run")
    def test_start_backtest_run_succeeds_with_active_event_loop(
            self,
            _mock_exec_run,
    ):
        self.mock_vcs.checkout.return_value = {
            "dynamic_quantity": "0.01",
            "assets": [
                {
                    "name": "Bitcoin",
                    "base_ticker_symbol": "BTC",
                    "quote_ticker_symbol": "USD",
                    "exchange": "CRYPTO_DOT_COM",
                    "min_quantity": 0.001,
                    "quote_decimals": 2,
                    "quantity_decimals": 4,
                    "candles_timeframe": "MIN1",
                    "schedule": 1,
                    "strategies": [],
                    "consensus": {"buy": 1.0, "sell": 0.5},
                }
            ],
        }

        spec = BacktestRunSpec(
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash="commit_hash_123",
            ),
        )

        async def run_async():
            return self.service.start_backtest_run(spec)

        session = asyncio.run(run_async())
        assert session is not None
        assert session.ticker_symbol == "BTC_USD"
