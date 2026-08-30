from src.backtest.execution.latency.fixed_latency import FixedLatencyModel


class TestFixedLatencyModel:
    def test_returns_configured_value(self):
        model = FixedLatencyModel(milliseconds=500.0)
        assert model.get_latency(None, "BTC_USD") == 0.5

    def test_zero_latency(self):
        model = FixedLatencyModel(milliseconds=0.0)
        assert model.get_latency(None, "BTC_USD") == 0.0

    def test_large_latency(self):
        model = FixedLatencyModel(milliseconds=2000.0)
        assert model.get_latency(None, "BTC_USD") == 2.0

    def test_independent_of_order_and_symbol(self):
        model = FixedLatencyModel(milliseconds=300.0)
        assert model.get_latency(None, "BTC_USD") == 0.3
        assert model.get_latency(None, "ETH_USD") == 0.3
