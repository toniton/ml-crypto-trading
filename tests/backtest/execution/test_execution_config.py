from decimal import Decimal
from unittest.mock import patch

from api.interfaces.asset import Asset
from api.interfaces.trade_action import TradeAction
from src.backtest.execution.config import build_execution_model
from src.configuration.application_config import ApplicationConfig
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum


def _make_asset(quote_decimals: int = 2) -> Asset:
    return Asset(
        base_ticker_symbol="BTC",
        quote_ticker_symbol="USD",
        quote_decimals=quote_decimals,
        name="Bitcoin",
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=0.001,
        quantity_decimals=3,
        schedule=0,
        candles_timeframe="MIN1",
    )


def _config(**kwargs) -> ApplicationConfig:
    kwargs.setdefault("trading_config_filepath", "config.yaml")
    with patch("sys.argv", ["pytest"]):
        return ApplicationConfig(**kwargs)


class TestBuildExecutionModel:
    def test_zero_values_are_preserved(self):
        model = build_execution_model(
            _config(
                backtest_latency_ms=0.0,
                backtest_slippage_ticks=0,
                backtest_fee_rate=0.0,
            )
        )

        assert model.latency.get_latency(None, "BTC_USD") == 0.0
        assert model.slippage.apply(TradeAction.BUY, Decimal("100.00"), _make_asset()) == Decimal("100.00")
        assert model.fees.calculate(Decimal("1000")) == Decimal("0")

    def test_defaults_apply_when_unset(self):
        model = build_execution_model(_config())

        assert model.latency.get_latency(None, "BTC_USD") == 0.5
        assert model.slippage.apply(TradeAction.BUY, Decimal("100.00"), _make_asset()) == Decimal("100.02")
        assert model.fees.calculate(Decimal("1000")) == Decimal("1")
