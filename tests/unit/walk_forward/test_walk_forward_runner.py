from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import yaml
from fastapi.testclient import TestClient

from api.interfaces.market_data import MarketData
from api.interfaces.walk_forward import (
    WalkForwardRunSpec,
    WalkForwardWindowSpec,
    WindowMode,
)
from src.agent import AgentGateway
from src.backtest.backtest_data_loader import HistoricalDataPoint
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.data.backtest_data_source_resolver import BacktestDataSourceResolver
from src.configuration.trading_config import TradingConfig
from src.core.interfaces.data_source import DataSource
from src.events.message_event_bus import MessageEventBus
from src.recorder.market_data_store import MarketDataStore
from src.server.app import ChatApp
from src.vcs.application.service import VCSService
from src.walk_forward.runner.walk_forward_runner import WalkForwardRunner
from tests.unit.agent.fakes import FakeLlmAdapter
from tests.unit.api_server.helpers import (
    make_temp_db_manager,
    make_test_llm_manager,
    make_test_trading_proxy,
)


class MockStaticDataSource(DataSource):
    def __init__(self, data_points: list[HistoricalDataPoint]):
        self._data_points = data_points

    def load(self, request) -> BacktestDataSet:
        filtered = self._data_points
        if request.start_time is not None:
            start_epoch = int(request.start_time.timestamp())
            filtered = [p for p in filtered if p.timestamp >= start_epoch]
        if request.end_time is not None:
            end_epoch = int(request.end_time.timestamp())
            filtered = [p for p in filtered if p.timestamp <= end_epoch]

        return BacktestDataSet(
            dataset_id="mock_data",
            ticker_symbol=request.ticker_symbol,
            start_time=datetime.fromtimestamp(min(p.timestamp for p in filtered), tz=timezone.utc),
            end_time=datetime.fromtimestamp(max(p.timestamp for p in filtered), tz=timezone.utc),
            data_points=tuple(filtered),
        )


def _build_test_points(count: int = 50) -> list[HistoricalDataPoint]:
    base_ts = 1700000000
    points = []
    price = Decimal("100.0")
    for i in range(count):
        points.append(
            HistoricalDataPoint(
                timestamp=base_ts + i * 60,
                open_price=price,
                high_price=price + Decimal("2.0"),
                low_price=price - Decimal("2.0"),
                close_price=price + Decimal("1.0"),
                volume=Decimal("1000.0"),
                market_cap=Decimal("5000000.0"),
            )
        )
        price += Decimal("0.5")
    return points


SAMPLE_CONFIG = """
assets:
  - name: "Bitcoin"
    base_ticker_symbol: "BTC"
    quote_ticker_symbol: "USD"
    exchange: "CRYPTO_DOT_COM"
    min_quantity: 0.00005
    quote_decimals: 2
    quantity_decimals: 5
    candles_timeframe: "MIN1"
    schedule: 1
    strategies:
      - name: "BreakoutBuy"
        type: "DYNAMIC"
        action: "BUY"
        expression: "close > 50"
        weight: 1.0
    consensus:
      buy: 0.5
      sell: 0.5
"""


class TestWalkForwardRunner(unittest.TestCase):
    def setUp(self):
        self.db = make_temp_db_manager()
        self.points = _build_test_points(50)
        self.mock_resolver = MagicMock(spec=BacktestDataSourceResolver)
        self.mock_resolver.resolve.return_value = MockStaticDataSource(self.points)

        parsed = TradingConfig.model_validate(yaml.safe_load(SAMPLE_CONFIG))
        self.asset = parsed.assets[0]

    def test_runs_walk_forward_with_clean_folds(self):
        runner = WalkForwardRunner(
            db_manager=self.db,
            assets={self.asset.ticker_symbol: self.asset},
            data_source_resolver=self.mock_resolver,
        )

        spec = WalkForwardRunSpec(
            ticker_symbol=self.asset.ticker_symbol,
            windows=WalkForwardWindowSpec(
                train_candle_count=15,
                test_candle_count=5,
                step_size_candles=5,
                warmup_candle_count=2,
                window_mode=WindowMode.ROLLING,
            ),
            initial_balance=Decimal("10000.0"),
        )

        summary = runner.run(spec)
        assert summary.total_folds > 0
        assert summary.total_folds == len(summary.fold_results)
        assert summary.profitable_fold_ratio >= 0.0
        assert summary.verdict != "NO_FOLDS_EVALUATED"

    def test_runs_walk_forward_with_candidate_and_baseline_weights(self):
        runner = WalkForwardRunner(
            db_manager=self.db,
            assets={self.asset.ticker_symbol: self.asset},
            data_source_resolver=self.mock_resolver,
        )

        spec = WalkForwardRunSpec(
            ticker_symbol=self.asset.ticker_symbol,
            windows=WalkForwardWindowSpec(
                train_candle_count=15,
                test_candle_count=5,
                step_size_candles=5,
                warmup_candle_count=2,
                window_mode=WindowMode.ROLLING,
            ),
            initial_balance=Decimal("10000.0"),
            candidate_weights={"BreakoutBuy": 2.0},
            baseline_weights={"BreakoutBuy": 0.5},
        )

        summary = runner.run(spec)
        assert summary.total_folds > 0
        first_fold = summary.fold_results[0]
        assert first_fold.baseline_test_return_pct is not None
        assert first_fold.equal_weight_test_return_pct is not None


class TestWalkForwardApi(unittest.TestCase):
    def setUp(self):
        self.db = make_temp_db_manager()
        self.vcs = VCSService(self.db)
        self.vcs.seed_if_empty(
            TradingConfig.model_validate(yaml.safe_load(SAMPLE_CONFIG)),
            author="test",
            message="seed",
        )
        self.agent = AgentGateway(FakeLlmAdapter(), vcs=self.vcs)
        self.store = MarketDataStore()
        # Seed market data store observations
        base_ts = 1700000000
        for i in range(40):
            self.store.record(
                "BTC_USD",
                MarketData(
                    close_price=Decimal("100.0") + Decimal(str(i)),
                    high_price=Decimal("105.0"),
                    low_price=Decimal("95.0"),
                    volume=Decimal("500.0"),
                    timestamp=float(base_ts + i * 60),
                ),
            )

        self.mock_engine = MagicMock()
        self.proxy = make_test_trading_proxy(
            trading_engine=self.mock_engine, market_data_store=self.store
        )
        self.app = ChatApp.create(
            trading_proxy=self.proxy,
            agent=self.agent,
            event_bus=MessageEventBus(),
            db_manager=self.db,
            vcs=self.vcs,
            llm_manager=make_test_llm_manager(self.db),
            retention_manager=MagicMock(),
        )
        self.client = TestClient(self.app)

    def test_start_and_get_walk_forward_run(self):
        payload = {
            "ticker_symbol": "BTC_USD",
            "windows": {
                "train_candle_count": 15,
                "test_candle_count": 5,
                "step_size_candles": 5,
                "warmup_candle_count": 2,
                "window_mode": "rolling",
            },
            "initial_balance": "10000.0",
        }
        res = self.client.post("/api/v1/walk-forward", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert "run_id" in data
        assert data["status"] == "RUNNING"

        run_id = data["run_id"]
        res_get = self.client.get(f"/api/v1/walk-forward/{run_id}")
        assert res_get.status_code == 200
        run_data = res_get.json()
        assert run_data["id"] == run_id
        assert run_data["ticker_symbol"] == "BTC_USD"

        res_list = self.client.get("/api/v1/walk-forward")
        assert res_list.status_code == 200
        runs = res_list.json()
        assert len(runs) >= 1

        self.app.state.walk_forward_service.wait_for_run(run_id, timeout=10.0)

    def test_cancel_walk_forward_run_via_api(self):
        payload = {
            "ticker_symbol": "BTC_USD",
            "windows": {
                "train_candle_count": 15,
                "test_candle_count": 5,
                "step_size_candles": 5,
                "warmup_candle_count": 2,
                "window_mode": "rolling",
            },
        }
        res = self.client.post("/api/v1/walk-forward", json=payload)
        assert res.status_code == 201
        run_id = res.json()["run_id"]

        cancel_res = self.client.post(f"/api/v1/walk-forward/{run_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["cancelled"] is True

        self.app.state.walk_forward_service.wait_for_run(run_id, timeout=5.0)
        run_info = self.app.state.walk_forward_service.get_run(run_id)
        assert run_info["status"] in ("CANCELLED", "COMPLETED")

