from decimal import Decimal

from backtest.execution.fees.percentage_fee import PercentageFee


class TestPercentageFee:
    def test_calculates_fee(self):
        model = PercentageFee(rate=Decimal("0.001"))
        assert model.calculate(Decimal("1000")) == Decimal("1.000")

    def test_zero_notional(self):
        model = PercentageFee(rate=Decimal("0.001"))
        assert model.calculate(Decimal("0")) == Decimal("0")

    def test_negative_notional(self):
        model = PercentageFee(rate=Decimal("0.001"))
        result = model.calculate(Decimal("-500"))
        assert result == Decimal("0.500")

    def test_ten_percent(self):
        model = PercentageFee(rate=Decimal("0.1"))
        assert model.calculate(Decimal("100")) == Decimal("10.0")

    def test_zero_rate(self):
        model = PercentageFee(rate=Decimal("0"))
        assert model.calculate(Decimal("10000")) == Decimal("0")
