from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

from api.interfaces.backtest_run_spec import (
    BacktestConfigurationSourceType,
    BacktestConfigurationSpec,
    BacktestExecutionSpec,
    BacktestMarketDataSpec,
)
from api.interfaces.walk_forward import WalkForwardRunSpec, WalkForwardSummary
from src.server.services.walk_forward_application_service import WalkForwardApplicationService


class TestWalkForwardApplicationService:
    def setup_method(self):
        self.mock_db = MagicMock()
        self.mock_uow = MagicMock()
        self.mock_db.get_unit_of_work.return_value.__enter__.return_value = self.mock_uow
        self.mock_repo = MagicMock()
        self.mock_uow.get_repository.return_value = self.mock_repo

        self.mock_vcs = MagicMock()
        self.mock_dataset = MagicMock()
        self.mock_store = MagicMock()

        self.mock_vcs.resolve_commit_hash.return_value = "immutable_hash_abc123"
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

        self.service = WalkForwardApplicationService(
            db_manager=self.mock_db,
            vcs_service=self.mock_vcs,
            market_data_store=self.mock_store,
            dataset_service=self.mock_dataset,
        )

    @patch("threading.Thread")
    def test_start_run_resolves_head_and_persists_resolved_commit_hash(self, mock_thread_cls):
        spec = WalkForwardRunSpec(
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash=None,
            ),
            candidate_weights={"Breakout": 1.5},
            baseline_weights={"Breakout": 1.0},
        )

        res = self.service.start_run(spec)

        self.mock_vcs.resolve_commit_hash.assert_called_once_with("HEAD")
        self.mock_vcs.checkout.assert_called_once_with("immutable_hash_abc123")
        assert res["vcs_commit_hash"] == "immutable_hash_abc123"
        assert res["spec"]["configuration"]["vcs_commit_hash"] == "immutable_hash_abc123"
        assert res["spec"]["software_version"] == "1.0.0"
        assert res["software_version"] == "1.0.0"

        self.mock_repo.save_run.assert_called_once()
        saved_call = self.mock_repo.save_run.call_args[1]
        assert saved_call["status"] == "RUNNING"
        assert saved_call["spec"]["configuration"]["vcs_commit_hash"] == "immutable_hash_abc123"
        assert saved_call["spec"]["software_version"] == "1.0.0"
        mock_thread_cls.return_value.start.assert_called_once()

    @patch("threading.Thread")
    def test_start_run_raises_when_initial_persistence_fails(self, mock_thread_cls):
        self.mock_repo.save_run.side_effect = Exception("DB Connection Refused")

        spec = WalkForwardRunSpec(
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash="HEAD",
            ),
        )

        with pytest.raises(RuntimeError) as exc_info:
            self.service.start_run(spec)

        assert "Failed to persist initial walk-forward run record" in str(exc_info.value)
        mock_thread_cls.return_value.start.assert_not_called()

    def test_execute_run_updates_summary_with_reproducibility_metadata(self):
        spec = WalkForwardRunSpec(
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash="resolved_commit_999",
            ),
            data_source=BacktestMarketDataSpec(dataset_id="ds_btc_2024"),
            execution=BacktestExecutionSpec(latency_ms=250.0, slippage_ticks=1, fee_rate=Decimal("0.0005")),
            candidate_weights={"StratA": 0.8},
            baseline_weights={"StratA": 0.5},
            software_version="1.0.0",
        )

        mock_runner = MagicMock()
        mock_summary = WalkForwardSummary(
            run_id="wf_test_123",
            ticker_symbol="BTC_USD",
            total_folds=2,
            profitable_folds=2,
            profitable_fold_ratio=1.0,
            aggregate_oos_return_pct=12.5,
            max_oos_drawdown_pct=3.0,
            walk_forward_efficiency=0.85,
            verdict="ROBUST",
            vcs_commit_hash="resolved_commit_999",
            dataset_identity="ds_btc_2024",
            execution_assumptions={"latency_ms": 250.0, "slippage_ticks": 1, "fee_rate": "0.0005"},
            strategy_weights={"candidate": {"StratA": 0.8}, "baseline": {"StratA": 0.5}},
            candidate_weights={"StratA": 0.8},
            baseline_weights={"StratA": 0.5},
            software_version="1.0.0",
        )
        mock_runner.run.return_value = mock_summary

        self.service._execute_run(mock_runner, spec, run_id="wf_test_123")

        self.mock_repo.update_run_summary.assert_called_once()
        call_kwargs = self.mock_repo.update_run_summary.call_args[1]
        assert call_kwargs["run_id"] == "wf_test_123"
        assert call_kwargs["status"] == "COMPLETED"
        summary = call_kwargs["summary"]
        assert summary["vcs_commit_hash"] == "resolved_commit_999"
        assert summary["dataset_identity"] == "ds_btc_2024"
        assert summary["software_version"] == "1.0.0"
        assert summary["strategy_weights"]["candidate"] == {"StratA": 0.8}

    def test_execute_run_records_metadata_on_failure(self):
        spec = WalkForwardRunSpec(
            ticker_symbol="BTC_USD",
            configuration=BacktestConfigurationSpec(
                source_type=BacktestConfigurationSourceType.VCS,
                vcs_commit_hash="resolved_commit_failed",
            ),
            data_source=BacktestMarketDataSpec(dataset_id="ds_btc_faulty"),
            execution=BacktestExecutionSpec(latency_ms=100.0),
            candidate_weights={"StratB": 0.7},
            software_version="1.0.0",
        )

        mock_runner = MagicMock()
        mock_runner.run.side_effect = ValueError("Insufficient candle observations")

        self.service._execute_run(mock_runner, spec, run_id="wf_failed_01")

        self.mock_repo.update_run_summary.assert_called_once()
        call_kwargs = self.mock_repo.update_run_summary.call_args[1]
        assert call_kwargs["run_id"] == "wf_failed_01"
        assert call_kwargs["status"] == "FAILED"
        summary = call_kwargs["summary"]
        assert "Insufficient candle observations" in summary["error"]
        assert summary["vcs_commit_hash"] == "resolved_commit_failed"
        assert summary["dataset_identity"] == "ds_btc_faulty"
        assert summary["software_version"] == "1.0.0"
        assert summary["strategy_weights"]["candidate"] == {"StratB": 0.7}
