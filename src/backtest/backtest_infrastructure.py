from __future__ import annotations

from dataclasses import dataclass

from src.backtest.backtest_clock import BacktestClock
from src.backtest.backtest_data_loader import BacktestDataLoader
from src.backtest.backtest_event_bus import BacktestEventBus
from src.backtest.execution.backtest_execution_engine import BacktestExecutionEngine


@dataclass
class BacktestInfrastructure:
    clock: BacktestClock
    loader: BacktestDataLoader
    bus: BacktestEventBus
    execution_engine: BacktestExecutionEngine
