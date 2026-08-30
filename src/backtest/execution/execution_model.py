from dataclasses import dataclass

from src.backtest.execution.latency.latency_model import LatencyModel
from src.backtest.execution.slippage.slippage_model import SlippageModel
from src.backtest.execution.fees.fee_model import FeeModel


@dataclass
class ExecutionModel:
    latency: LatencyModel
    slippage: SlippageModel
    fees: FeeModel
