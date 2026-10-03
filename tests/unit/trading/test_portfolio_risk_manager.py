from __future__ import annotations

from decimal import Decimal

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.market_data import MarketData
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.events.message_event_bus import MessageEventBus
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.events import (
    BalanceChangedEvent,
    OrderFilledEvent,
    OrderSubmittedEvent,
)
from src.trading.protection.portfolio_risk_manager import PortfolioRiskManager
from src.trading.protection.quote_portfolio import QuotePortfolio


def _make_asset(base: str, quote: str, exchange: ExchangeProvidersEnum = ExchangeProvidersEnum.CCXT_KRAKEN) -> Asset:
    return Asset(
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        quote_decimals=2,
        name=f"{base}/{quote}",
        exchange=exchange,
        min_quantity=0.01,
        quantity_decimals=4,
        schedule=AssetSchedule.EVERY_MINUTE,
        candles_timeframe=Timeframe.MIN1,
    )


def test_quote_portfolio_cash_reservation_lifecycle():
    portfolio = QuotePortfolio(exchange="KRAKEN", quote_currency="USD")
    portfolio.update_cash(Decimal("10.00"))

    assert portfolio.available_cash == Decimal("10.00")
    assert portfolio.reserved_cash == Decimal("0.00")

    # Reserve $4.00 for order-1
    assert portfolio.reserve_cash("order-1", Decimal("4.00")) is True
    assert portfolio.available_cash == Decimal("6.00")
    assert portfolio.reserved_cash == Decimal("4.00")

    # Attempt to reserve $7.00 (exceeds $6.00 available) -> fails
    assert portfolio.reserve_cash("order-2", Decimal("7.00")) is False
    assert portfolio.available_cash == Decimal("6.00")

    # Reserve $5.00 for order-3 -> succeeds
    assert portfolio.reserve_cash("order-3", Decimal("5.00")) is True
    assert portfolio.available_cash == Decimal("1.00")
    assert portfolio.reserved_cash == Decimal("9.00")

    # Release order-1 ($4.00)
    released = portfolio.release_cash("order-1")
    assert released == Decimal("4.00")
    assert portfolio.available_cash == Decimal("5.00")
    assert portfolio.reserved_cash == Decimal("5.00")

    # Release order-3 ($5.00)
    released = portfolio.release_cash("order-3")
    assert released == Decimal("5.00")
    assert portfolio.available_cash == Decimal("10.00")
    assert portfolio.reserved_cash == Decimal("0.00")


def test_quote_portfolio_multi_asset_mark_to_market_equity():
    portfolio = QuotePortfolio(exchange="KRAKEN", quote_currency="USD")
    portfolio.update_cash(Decimal("7.61"))

    portfolio.update_asset_position("BTC_USD", Decimal("0.001"))
    portfolio.update_asset_mark_price("BTC_USD", Decimal("60000.00"))  # $60.00

    portfolio.update_asset_position("DOGE_USD", Decimal("500.0"))
    portfolio.update_asset_mark_price("DOGE_USD", Decimal("0.10"))  # $50.00

    portfolio.update_asset_position("CRO_USD", Decimal("1000.0"))
    portfolio.update_asset_mark_price("CRO_USD", Decimal("0.08"))  # $80.00

    # Total Equity = 7.61 + 60.00 + 50.00 + 80.00 = 197.61
    assert portfolio.get_total_equity() == Decimal("197.61")
    assert portfolio.peak_equity == Decimal("197.61")
    assert portfolio.get_drawdown() == Decimal("0.0")

    # Asset concentration
    # BTC = 60.00 / 197.61 ≈ 0.3036
    btc_conc = portfolio.get_asset_concentration("BTC_USD")
    assert round(btc_conc, 4) == Decimal("0.3036")


def test_portfolio_risk_manager_drawdown_limit():
    btc = _make_asset("BTC", "USD")
    risk_manager = PortfolioRiskManager(assets=[btc], max_portfolio_drawdown=Decimal("0.15"))  # 15% max DD

    # Initialize portfolio with peak equity of $200.00
    risk_manager.update_cash_balance(btc.exchange.value, "USD", Decimal("200.00"))
    port = risk_manager.get_portfolio(btc.exchange.value, "USD")
    assert port.peak_equity == Decimal("200.00")

    # Cash drops to $160.00 (20% drawdown > 15% limit)
    risk_manager.update_cash_balance(btc.exchange.value, "USD", Decimal("160.00"))
    assert port.get_drawdown() == Decimal("-0.20")

    can_trade, reason = risk_manager.can_trade(btc, TradeAction.BUY, Decimal("10.00"))
    assert can_trade is False
    assert "Portfolio drawdown limit exceeded" in reason

    # SELL actions should always be permitted to reduce risk
    can_sell, _ = risk_manager.can_trade(btc, TradeAction.SELL, Decimal("10.00"))
    assert can_sell is True


def test_portfolio_risk_manager_concentration_limit():
    btc = _make_asset("BTC", "USD")
    doge = _make_asset("DOGE", "USD")
    risk_manager = PortfolioRiskManager(
        assets=[btc, doge],
        max_asset_concentration=Decimal("0.40"),  # 40% max in single asset
    )

    # Portfolio has $100.00 total equity ($70 cash + $30 in DOGE)
    risk_manager.update_cash_balance(btc.exchange.value, "USD", Decimal("70.00"))
    risk_manager.update_position(doge, Decimal("300"))
    market_data_doge = MarketData(
        timestamp=1700000000.0,
        close_price=Decimal("0.10"),
        high_price=Decimal("0.10"),
        low_price=Decimal("0.10"),
        volume=Decimal("100"),
    )
    risk_manager.update_market_data(doge, market_data_doge)

    # Proposed BUY of $15 DOGE -> projected notional = $30 + $15 = $45 / $100 = 45% > 40%
    can_trade, reason = risk_manager.can_trade(doge, TradeAction.BUY, Decimal("15.00"), market_data_doge)
    assert can_trade is False
    assert "Asset concentration limit exceeded" in reason

    # Proposed BUY of $5 BTC -> projected notional = $5 / $100 = 5% <= 40%
    can_trade_btc, _ = risk_manager.can_trade(btc, TradeAction.BUY, Decimal("5.00"))
    assert can_trade_btc is True


def test_portfolio_risk_manager_event_bus_cash_reservation_lifecycle():
    event_bus = MessageEventBus()
    btc = _make_asset("BTC", "USD")
    doge = _make_asset("DOGE", "USD")

    risk_manager = PortfolioRiskManager(assets=[btc, doge], event_bus=event_bus)
    risk_manager.update_cash_balance(btc.exchange.value, "USD", Decimal("100.00"))

    order = Order(
        uuid="buy-btc-001",
        provider_name=btc.exchange.value,
        ticker_symbol="BTC_USD",
        price=Decimal("50000.00"),
        quantity="0.001",  # $50.00
        trade_action=TradeAction.BUY,
        created_time=1700000000.0,
    )

    # 1. Order submitted -> cash reserved
    event_bus.publish(OrderSubmittedEvent(symbol="BTC_USD", order=order))
    port = risk_manager.get_portfolio(btc.exchange.value, "USD")
    assert port.reserved_cash == Decimal("50.00")
    assert port.available_cash == Decimal("50.00")

    # 2. Order filled -> cash unreserved
    order.status = OrderStatus.COMPLETED
    event_bus.publish(OrderFilledEvent(symbol="BTC_USD", order=order))
    assert port.reserved_cash == Decimal("0.00")
    assert port.available_cash == Decimal("100.00")


def test_portfolio_risk_manager_uses_exchange_available_over_total():
    event_bus = MessageEventBus()
    btc = _make_asset("BTC", "USD")
    risk_manager = PortfolioRiskManager(assets=[btc], event_bus=event_bus)

    event_bus.publish(BalanceChangedEvent(
        exchange=btc.exchange.value,
        currency="USD",
        available=Decimal("70.00"),
        total=Decimal("100.00"),
    ))

    port = risk_manager.get_portfolio(btc.exchange.value, "USD")
    assert port.total_cash == Decimal("70.00")
    assert port.available_cash == Decimal("70.00")


def test_portfolio_risk_manager_local_reservation_with_exchange_balance_update():
    event_bus = MessageEventBus()
    btc = _make_asset("BTC", "USD")
    risk_manager = PortfolioRiskManager(assets=[btc], event_bus=event_bus)

    port = risk_manager.get_portfolio(btc.exchange.value, "USD")
    port.update_cash(Decimal("100.00"))
    port.reserve_cash("order-local-1", Decimal("20.00"))

    event_bus.publish(BalanceChangedEvent(
        exchange=btc.exchange.value,
        currency="USD",
        available=Decimal("70.00"),
        total=Decimal("100.00"),
    ))

    assert port.total_cash == Decimal("70.00")
    assert port.reserved_cash == Decimal("20.00")
    assert port.available_cash == Decimal("50.00")


def test_portfolio_reconciliation_cleans_orphaned_reservations():
    btc = _make_asset("BTC", "USD")
    risk_manager = PortfolioRiskManager(assets=[btc])
    port = risk_manager.get_portfolio(btc.exchange.value, "USD")

    port.update_cash(Decimal("100.00"))
    port.reserve_cash("order-active", Decimal("30.00"))
    port.reserve_cash("order-orphaned", Decimal("20.00"))

    released = risk_manager.reconcile_open_orders(active_order_uuids={"order-active"})

    assert released == Decimal("20.00")
    assert port.reserved_cash == Decimal("30.00")
    assert port.available_cash == Decimal("70.00")

