from decimal import Decimal

from src.configuration.application_config import ApplicationConfig
from src.backtest.execution.execution_model import ExecutionModel
from src.backtest.execution.latency.fixed_latency import FixedLatencyModel
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from src.backtest.execution.fees.percentage_fee import PercentageFee


def build_execution_model(config: ApplicationConfig) -> ExecutionModel:
    # Use `is not None` (not `or`) so an explicit zero (latency/slippage/fees) is a
    # valid deterministic baseline instead of silently falling back to the default.
    latency_ms = config.backtest_latency_ms if config.backtest_latency_ms is not None else 500.0
    slippage_ticks = config.backtest_slippage_ticks if config.backtest_slippage_ticks is not None else 2
    fee_rate = Decimal(
        str(config.backtest_fee_rate if config.backtest_fee_rate is not None else 0.001)
    )
    return ExecutionModel(
        latency=FixedLatencyModel(latency_ms),
        slippage=FixedTickSlippage(slippage_ticks),
        fees=PercentageFee(fee_rate),
    )
