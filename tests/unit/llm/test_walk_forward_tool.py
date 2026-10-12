from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from api.interfaces.walk_forward import WalkForwardRunSpec, WalkForwardSummary
from src.llm.tools.walk_forward_tool import WalkForwardTool
from src.server.services.walk_forward_application_service import (
    WalkForwardApplicationService,
)
from src.trading.analytics.strategy_optimizer import StrategyOptimizer
from src.walk_forward.runner.walk_forward_runner import WalkForwardRunner


# pylint: disable=protected-access
class TestWalkForwardTool(unittest.TestCase):
    def setUp(self):
        self.mock_service = MagicMock(spec=WalkForwardApplicationService)
        self.tool = WalkForwardTool(walk_forward_service=self.mock_service)

    def test_list_runs_empty(self):
        self.mock_service.list_runs.return_value = []
        result = self.tool._run(action="list")
        self.assertIn("No previous walk-forward runs found", result)

    def test_list_runs_populated(self):
        self.mock_service.list_runs.return_value = [
            {
                "run_id": "wf_12345",
                "ticker_symbol": "BTC_USD",
                "status": "COMPLETED",
                "performance_summary": {
                    "out_of_sample_return_pct": 12.5,
                    "walk_forward_efficiency_ratio": 0.75,
                    "stability_classification": "ROBUST",
                },
            }
        ]
        result = self.tool._run(action="list")
        self.assertIn("wf_12345", result)
        self.assertIn("BTC_USD", result)
        self.assertIn("ROBUST", result)
        self.assertIn("+12.50%", result)

    def test_get_run_not_found(self):
        self.mock_service.get_run.return_value = None
        result = self.tool._run(action="get", run_id="wf_missing")
        self.assertIn("not found", result)

    def test_get_run_still_running(self):
        self.mock_service.get_run.return_value = {
            "run_id": "wf_running",
            "ticker_symbol": "ETH_USD",
            "status": "RUNNING",
        }
        result = self.tool._run(action="get", run_id="wf_running")
        self.assertIn("still running", result)

    def test_get_run_failed(self):
        self.mock_service.get_run.return_value = {
            "run_id": "wf_failed",
            "ticker_symbol": "ETH_USD",
            "status": "FAILED",
            "performance_summary": {"error": "Insufficient historical points"},
        }
        result = self.tool._run(action="get", run_id="wf_failed")
        self.assertIn("failed: Insufficient historical points", result)

    def test_get_run_completed(self):
        self.mock_service.get_run.return_value = {
            "run_id": "wf_done",
            "ticker_symbol": "BTC_USD",
            "status": "COMPLETED",
            "performance_summary": {
                "stability_classification": "ROBUST",
                "out_of_sample_return_pct": 8.4,
                "in_sample_return_pct": 10.2,
                "walk_forward_efficiency_ratio": 0.82,
                "max_out_of_sample_drawdown_pct": 3.5,
                "profitable_folds": 4,
                "total_folds": 5,
                "profitable_fold_ratio": 0.8,
                "baseline_return_pct": 2.1,
                "excess_return_vs_baseline_pct": 6.3,
                "folds": [
                    {
                        "fold_index": 1,
                        "in_sample_return_pct": 5.0,
                        "out_of_sample_return_pct": 4.0,
                        "out_of_sample_trades": 12,
                        "out_of_sample_win_rate_pct": 60.0,
                    }
                ],
            },
        }
        result = self.tool._run(action="get", run_id="wf_done")
        self.assertIn("ROBUST", result)
        self.assertIn("+8.40%", result)
        self.assertIn("0.82", result)
        self.assertIn("Fold #1", result)

    def test_start_run_requires_ticker(self):
        result = self.tool._run(action="start", ticker_symbol=None)
        self.assertIn("Error: 'ticker_symbol' is required", result)

    def test_start_run_success(self):
        self.mock_service.start_run.return_value = {
            "run_id": "wf_new_123",
            "status": "RUNNING",
        }
        result = self.tool._run(
            action="start",
            ticker_symbol="BTC_USD",
            window_mode="rolling",
            train_window_days=45,
            test_window_days=15,
        )
        self.assertIn("wf_new_123", result)
        self.assertIn("BTC_USD", result)
        self.assertIn("45d in-sample / 15d out-of-sample", result)

    def test_strategy_optimizer_walk_forward_bridge(self):
        mock_runner = MagicMock(spec=WalkForwardRunner)
        mock_spec = MagicMock(spec=WalkForwardRunSpec)
        mock_summary = MagicMock(spec=WalkForwardSummary)
        mock_runner.run.return_value = mock_summary

        summary = StrategyOptimizer.evaluate_walk_forward_baseline(mock_runner, mock_spec)
        self.assertEqual(summary, mock_summary)
        mock_runner.run.assert_called_once_with(mock_spec)
