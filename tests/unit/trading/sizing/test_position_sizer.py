from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.asset import Asset
from api.interfaces.market_data import MarketData
from api.interfaces.trade_action import TradeAction
from api.interfaces.trading_context import TradingContext
from src.configuration.trading_config import TradingConfig
from src.trading.consensus.consensus_decision import ConsensusDecision
from src.trading.sizing.position_sizer import PositionSizer


def _asset(min_qty=0.001, decimals=3, dynamic_quantity=None):
    asset = MagicMock(spec=Asset)
    asset.min_quantity = min_qty
    asset.quantity_decimals = decimals
    asset.dynamic_quantity = dynamic_quantity
    asset.ticker_symbol = "BTC_USD"
    asset.key = 1
    asset.exchange = MagicMock()
    asset.exchange.value = "BACKTEST"
    return asset


def _market(price="100", volume="500"):
    return MarketData(
        volume=Decimal(volume),
        high_price=Decimal("110"),
        low_price=Decimal("90"),
        close_price=Decimal(price),
        timestamp=1000.0,
    )


def _decision(action=TradeAction.BUY):
    return ConsensusDecision(action, "BTC_USD", {"s1": True}, {"s1": 1.0}, 1.3)


def test_position_sizer_defaults_to_min_quantity_when_no_formula():
    sizer = PositionSizer()
    asset = _asset()
    ctx = TradingContext("BTC_USD", "BACKTEST", Decimal("1000"))
    balance = AccountBalance("USD", Decimal("1000"))

    qty = sizer.calculate_quantity(
        asset=asset,
        market_data=_market(),
        decision=_decision(),
        account_balance=balance,
        trading_context=ctx,
        candles=[],
    )
    assert qty == Decimal("0.001")


def test_position_sizer_evaluates_global_expression():
    sizer = PositionSizer(global_formula="volume / 100")
    asset = _asset()
    ctx = TradingContext("BTC_USD", "BACKTEST", Decimal("1000"))
    balance = AccountBalance("USD", Decimal("1000"))

    # volume 500 / 100 = 5.0
    qty = sizer.calculate_quantity(
        asset=asset,
        market_data=_market(volume="500"),
        decision=_decision(),
        account_balance=balance,
        trading_context=ctx,
        candles=[],
    )
    assert qty == Decimal("5.000")


def test_position_sizer_asset_formula_overrides_global():
    asset = _asset(dynamic_quantity="volume / 50")
    sizer = PositionSizer(global_formula="volume / 100", assets=[asset])
    ctx = TradingContext("BTC_USD", "BACKTEST", Decimal("1000"))
    balance = AccountBalance("USD", Decimal("1000"))

    # Asset specific: 500 / 50 = 10.0
    qty = sizer.calculate_quantity(
        asset=asset,
        market_data=_market(volume="500"),
        decision=_decision(),
        account_balance=balance,
        trading_context=ctx,
        candles=[],
    )
    assert qty == Decimal("10.000")


def test_position_sizer_updates_from_config():
    sizer = PositionSizer(global_formula="volume / 100")
    config = TradingConfig.model_validate({
        "assets": [],
        "dynamic_quantity": "volume / 10",
    })
    sizer.update_config(config)
    assert sizer.global_formula == "volume / 10"
