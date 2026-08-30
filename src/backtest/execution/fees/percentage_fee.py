from decimal import Decimal


class PercentageFee:
    def __init__(self, rate: Decimal = Decimal("0.001")):
        self._rate = rate

    def calculate(self, notional: Decimal) -> Decimal:
        return abs(notional) * self._rate
