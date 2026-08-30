from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.trade_action import TradeAction
from src.backtest.execution.slippage.fixed_tick_slippage import FixedTickSlippage
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


class TestFixedTickSlippage:
    def test_buy_adds_slippage(self):
        model = FixedTickSlippage(ticks=2)
        asset = _make_asset(quote_decimals=2)
        result = model.apply(TradeAction.BUY, Decimal("100.00"), asset)
        assert result == Decimal("100.02")

    def test_sell_subtracts_slippage(self):
        model = FixedTickSlippage(ticks=2)
        asset = _make_asset(quote_decimals=2)
        result = model.apply(TradeAction.SELL, Decimal("100.00"), asset)
        assert result == Decimal("99.98")

    def test_zero_ticks(self):
        model = FixedTickSlippage(ticks=0)
        asset = _make_asset(quote_decimals=2)
        assert model.apply(TradeAction.BUY, Decimal("100.00"), asset) == Decimal("100.00")
        assert model.apply(TradeAction.SELL, Decimal("100.00"), asset) == Decimal("100.00")

    def test_different_decimals(self):
        model = FixedTickSlippage(ticks=1)
        asset = _make_asset(quote_decimals=4)
        result = model.apply(TradeAction.BUY, Decimal("100.00"), asset)
        assert result == Decimal("100.0001")

    def test_large_tick(self):
        model = FixedTickSlippage(ticks=3)
        asset = _make_asset(quote_decimals=0)
        result = model.apply(TradeAction.SELL, Decimal("1000.00"), asset)
        assert result == Decimal("997.00")
