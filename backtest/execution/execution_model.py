from dataclasses import dataclass

from backtest.execution.latency.latency_model import LatencyModel
from backtest.execution.slippage.slippage_model import SlippageModel
from backtest.execution.fees.fee_model import FeeModel


@dataclass
class ExecutionModel:
    latency: LatencyModel
    slippage: SlippageModel
    fees: FeeModel
