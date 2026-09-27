from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.account_balance import AccountBalance
from api.interfaces.candle import Candle
from api.interfaces.fees import Fees
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.trade_action import TradeAction
from src.exchange.interfaces.exchange_rest_manager import ExchangeRestManager
from src.llm.tools.exchange_read_tool import ExchangeReadOnlyTool


def test_fetch_balances():
    mock_rest = MagicMock(spec=ExchangeRestManager)
    mock_rest.get_account_balance.return_value = [
        AccountBalance(currency="USD", available_balance=Decimal("1500.50")),
        AccountBalance(currency="BTC", available_balance=Decimal("0.25")),
        AccountBalance(currency="ETH", available_balance=Decimal("0.0")),
    ]
    tool = ExchangeReadOnlyTool(rest_manager=mock_rest)
    result = tool._run(operation="get_balances", exchange="CRYPTO_DOT_COM")

    assert "Live Account Balances for CRYPTO_DOT_COM:" in result
    assert "BTC: 0.25" in result
    assert "USD: 1500.5" in result
    assert "ETH" not in result  # Zero balances omitted


def test_fetch_ticker():
    mock_rest = MagicMock(spec=ExchangeRestManager)
    mock_rest.get_market_data.return_value = MarketData(
        close_price=Decimal("65000.00"),
        high_price=Decimal("66000.00"),
        low_price=Decimal("64000.00"),
        volume=Decimal("123.45"),
        timestamp=1700000000.0,
    )
    tool = ExchangeReadOnlyTool(rest_manager=mock_rest)
    result = tool._run(operation="get_ticker", exchange="BINANCE", ticker_symbol="BTC_USD")

    assert "Market Data for BTC_USD on BINANCE:" in result
    assert "Mark Price: $65000" in result
    assert "24h High:   $66000" in result


def test_fetch_candles():
    mock_rest = MagicMock(spec=ExchangeRestManager)
    mock_rest.get_candles.return_value = [
        Candle(
            open=Decimal("100"), high=Decimal("105"), low=Decimal("95"),
            close=Decimal("102"), start_time=1700000000.0
        )
    ]
    tool = ExchangeReadOnlyTool(rest_manager=mock_rest)
    result = tool._run(operation="get_candles", exchange="KRAKEN", ticker_symbol="ETH_USD", timeframe="MIN5")

    assert "Recent Candles for ETH_USD (MIN5) on KRAKEN" in result
    assert "C: 102" in result


def test_fetch_open_orders():
    mock_rest = MagicMock(spec=ExchangeRestManager)
    order = MagicMock(spec=Order)
    order.uuid = "order-abc-123"
    order.ticker_symbol = "BTC_USD"
    order.trade_action = TradeAction.BUY
    order.quantity = "0.05"
    order.price = "64500.00"
    order.status = "OPEN"

    mock_rest.get_open_orders.return_value = [order]
    tool = ExchangeReadOnlyTool(rest_manager=mock_rest)
    result = tool._run(operation="get_open_orders", exchange="BINANCE")

    assert "Open Orders on BINANCE (1 active):" in result
    assert "UUID: order-abc-123" in result
    assert "BUY" in result


def test_fetch_fees():
    mock_rest = MagicMock(spec=ExchangeRestManager)
    mock_rest.get_instrument_fees.return_value = Fees(
        maker_fee_pct=Decimal("0.00075"),
        taker_fee_pct=Decimal("0.0015"),
    )
    tool = ExchangeReadOnlyTool(rest_manager=mock_rest)
    result = tool._run(operation="get_instrument_fees", exchange="BINANCE", ticker_symbol="BTC_USDT")

    assert "Trading Fees for BTC_USDT on BINANCE:" in result
    assert "Maker Fee: 0.075%" in result
    assert "Taker Fee: 0.15%" in result


def test_unsupported_operation():
    mock_rest = MagicMock(spec=ExchangeRestManager)
    tool = ExchangeReadOnlyTool(rest_manager=mock_rest)
    result = tool._run(operation="place_order", exchange="BINANCE")
    assert "Error: Unsupported operation 'place_order'" in result
