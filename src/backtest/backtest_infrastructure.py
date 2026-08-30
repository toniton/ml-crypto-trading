from __future__ import annotations

from dataclasses import dataclass

from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.data.backtest_data_set import BacktestDataSet
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine


@dataclass
class BacktestInfrastructure:
    clock: BacktestClock
    datasets: dict[str, BacktestDataSet]
    bus: BacktestEventBus
    execution_engine: BacktestExecutionEngine
