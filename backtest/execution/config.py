from decimal import Decimal

from src.configuration.application_config import ApplicationConfig
from backtest.execution.execution_model import ExecutionModel
from backtest.execution.latency.fixed_latency import FixedLatencyModel
from backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
from backtest.execution.fees.percentage_fee import PercentageFee


def build_execution_model(config: ApplicationConfig) -> ExecutionModel:
    latency_ms = config.backtest_latency_ms or 500.0
    slippage_ticks = config.backtest_slippage_ticks or 2
    fee_rate = Decimal(str(config.backtest_fee_rate or 0.001))
    return ExecutionModel(
        latency=FixedLatencyModel(latency_ms),
        slippage=FixedTickSlippage(slippage_ticks),
        fees=PercentageFee(fee_rate),
    )
