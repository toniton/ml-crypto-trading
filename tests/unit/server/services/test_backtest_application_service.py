from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
import pytest

from api.interfaces.backtest_run_spec import (
    BacktestConfigurationSourceType,
    BacktestConfigurationSpec,
    BacktestRunSpec,
)
from src.core.interfaces.execution_status import ExecutionStatus
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

    def _valid_config(self):
        return {
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

    def test_start_backtest_run_rejects_duplicate_active_session_id(self):
        self.mock_repo.is_session_active.return_value = True
        self.mock_vcs.checkout.return_value = self._valid_config()
        spec = BacktestRunSpec(
            session_id="bt_existing_active",
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash="HEAD",
            ),
        )

        with pytest.raises(ValueError) as exc_info:
            self.service.start_backtest_run(spec)

        assert "already active" in str(exc_info.value)

    @patch("threading.Thread")
    def test_concurrency_limit_leaves_excess_runs_queued(self, mock_thread_cls):
        self.service._max_concurrent_runs = 1
        self.service._active_runs.add("bt_busy_run")
        self.mock_vcs.checkout.return_value = self._valid_config()

        spec = BacktestRunSpec(
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash="HEAD",
            ),
        )

        session = self.service.start_backtest_run(spec)

        assert session.status == ExecutionStatus.QUEUED
        mock_thread_cls.return_value.start.assert_not_called()
        self.mock_repo.save_session.assert_called_once()

    def test_cancel_session_queued_and_running(self):
        self.mock_repo.mark_cancelled.return_value = True
        self.service._active_runs.add("bt_cancel_me")

        success = self.service.cancel_session("bt_cancel_me", reason="User cancel")

        assert success is True
        assert "bt_cancel_me" not in self.service._active_runs
        self.mock_repo.mark_cancelled.assert_called_once_with("bt_cancel_me", reason="User cancel")
        assert self.service._is_session_cancelled("bt_cancel_me") is True

    def test_recover_on_startup_recovers_abandoned_sessions(self):
        self.mock_repo.recover_abandoned_sessions.return_value = ["bt_rec_1", "bt_rec_2"]

        recovered = self.service.recover_on_startup()

        assert recovered == ["bt_rec_1", "bt_rec_2"]
        self.mock_repo.recover_abandoned_sessions.assert_called_once_with(timeout_seconds=120)

