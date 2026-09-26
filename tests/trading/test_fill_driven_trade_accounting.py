from decimal import Decimal
from unittest.mock import MagicMock

from api.interfaces.asset import Asset
from api.interfaces.asset_schedule import AssetSchedule
from api.interfaces.order import Order
from api.interfaces.timeframe import Timeframe
from api.interfaces.trade_action import OrderStatus, TradeAction
from src.exchange.interfaces.exchange_rest_manager import ExchangeProvidersEnum
from src.trading.events import PositionChangedEvent
from src.trading.orders.order_manager import OrderManager
from src.trading.session.in_memory_trading_journal import InMemoryTradingJournal
from src.trading.session.session_manager import SessionManager


def _create_test_asset(base: str = "BTC", quote: str = "USD") -> Asset:
    return Asset(
        name=f"{base}/{quote}",
        base_ticker_symbol=base,
        quote_ticker_symbol=quote,
        exchange=ExchangeProvidersEnum.CRYPTO_DOT_COM,
        min_quantity=0.001,
        quote_decimals=2,
        quantity_decimals=3,
        candles_timeframe=Timeframe.MIN1,
        schedule=AssetSchedule.EVERY_MINUTE,
        enabled=True,
    )


def test_session_manager_buy_fill_creates_lot_and_position_entry():
    session_mgr = SessionManager()
    session_mgr.create_session("sess_1").start_session()
    asset = _create_test_asset()
    session_mgr.init_asset_balance(asset, starting_balance=Decimal("1000"))

    buy_order = Order(
        uuid="order_buy_1",
        provider_name="simulated",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="0.1",
        trade_action=TradeAction.BUY,
        created_time=100.0,
        executed_time=101.0,
        fill_price=Decimal("50000"),
        fees=Decimal("2.5"),
        status=OrderStatus.COMPLETED,
    )

    trades = session_mgr.record_order_fill(buy_order)

    ctx = session_mgr.get_trading_context_by_symbol("BTC_USD")
    assert trades == []
    assert ctx.position_qty == Decimal("0.1")
    assert ctx.avg_entry_price == Decimal("50000")
    assert len(ctx.open_positions) == 1
    assert len(ctx.position_lots) == 1
    assert ctx.position_lots[0].fee_per_unit == Decimal("25")


def test_session_manager_sell_fill_matches_fifo_and_calculates_net_pnl():
    session_mgr = SessionManager()
    session_mgr.create_session("sess_1").start_session()
    asset = _create_test_asset()
    session_mgr.init_asset_balance(asset, starting_balance=Decimal("1000"))

    buy_order = Order(
        uuid="order_buy_1",
        provider_name="simulated",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="0.2",
        trade_action=TradeAction.BUY,
        created_time=100.0,
        executed_time=101.0,
        fill_price=Decimal("50000"),
        fees=Decimal("2.0"),
        status=OrderStatus.COMPLETED,
    )
    session_mgr.record_order_fill(buy_order)

    sell_order = Order(
        uuid="order_sell_1",
        provider_name="simulated",
        ticker_symbol="BTC_USD",
        price=Decimal("55000"),
        quantity="0.1",
        trade_action=TradeAction.SELL,
        created_time=110.0,
        executed_time=111.0,
        fill_price=Decimal("55000"),
        fees=Decimal("1.5"),
        status=OrderStatus.COMPLETED,
    )
    trades = session_mgr.record_order_fill(sell_order)

    ctx = session_mgr.get_trading_context_by_symbol("BTC_USD")
    assert len(trades) == 1
    trade = trades[0]
    assert trade.entry_order_uuid == "order_buy_1"
    assert trade.exit_order_uuid == "order_sell_1"
    assert trade.gross_pnl == Decimal("500")  # (55000 - 50000) * 0.1
    assert trade.fees == Decimal("2.5")  # entry_fee(1.0) + exit_fee(1.5)
    assert trade.net_pnl == Decimal("497.5")
    assert ctx.realized_pnl == Decimal("497.5")
    assert ctx.position_qty == Decimal("0.1")
    assert ctx.position_lots[0].remaining_quantity == Decimal("0.1")


def test_order_manager_fill_triggers_position_changed_event():
    db_mgr = MagicMock()
    uow = MagicMock()
    db_mgr.get_unit_of_work.return_value.__enter__.return_value = uow
    event_bus = MagicMock()
    journal = InMemoryTradingJournal()
    session_mgr = SessionManager()
    session_mgr.create_session("sess_1").start_session()
    asset = _create_test_asset()
    session_mgr.init_asset_balance(asset, starting_balance=Decimal("1000"))

    order_mgr = OrderManager(
        database_manager=db_mgr,
        trading_journal=journal,
        rest_manager=MagicMock(),
        websocket_manager=MagicMock(),
        synchronous_execution=True,
        event_bus=event_bus,
        session_manager=session_mgr,
    )

    buy_order = Order(
        uuid="order_1",
        provider_name="simulated",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="0.1",
        trade_action=TradeAction.BUY,
        created_time=100.0,
        executed_time=101.0,
        fill_price=Decimal("50000"),
        fees=Decimal("1.0"),
        status=OrderStatus.COMPLETED,
    )

    order_mgr._save_orders_to_database([buy_order])

    position_events = [
        call.args[0]
        for call in event_bus.publish.call_args_list
        if isinstance(call.args[0], PositionChangedEvent)
    ]
    assert len(position_events) == 1
    assert position_events[0].position_qty == Decimal("0.1")
    assert position_events[0].symbol == "BTC_USD"


def test_order_manager_has_outstanding_intent():
    db_mgr = MagicMock()
    uow = MagicMock()
    repo = MagicMock()
    uow.get_repository.return_value = repo
    db_mgr.get_unit_of_work.return_value.__enter__.return_value = uow

    order_mgr = OrderManager(
        database_manager=db_mgr,
        trading_journal=InMemoryTradingJournal(),
        rest_manager=MagicMock(),
        websocket_manager=MagicMock(),
        session_manager=MagicMock(),
        event_bus=MagicMock(),
        synchronous_execution=False,
    )

    assert not order_mgr.has_outstanding_intent("BTC_USD", TradeAction.BUY)

    pending_order = Order(
        uuid="ord_pending",
        provider_name="simulated",
        ticker_symbol="BTC_USD",
        price=Decimal("50000"),
        quantity="0.1",
        trade_action=TradeAction.BUY,
        created_time=100.0,
        status=OrderStatus.PENDING,
    )
    repo.get_non_terminal.return_value = [pending_order]

    assert order_mgr.has_outstanding_intent("BTC_USD", TradeAction.BUY)
    assert not order_mgr.has_outstanding_intent("BTC_USD", TradeAction.SELL)
    assert not order_mgr.has_outstanding_intent("ETH_USD", TradeAction.BUY)
