from decimal import Decimal

from src.backtest.execution.fees.fee_model import FeeModel


class PercentageFee(FeeModel):
    def __init__(self, rate: Decimal = Decimal("0.001")):
        self._rate = rate

    def calculate(self, notional: Decimal) -> Decimal:
        return abs(notional) * self._rate
